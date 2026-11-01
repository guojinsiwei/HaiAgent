"""Single-attempt Recuris execution; official reward and adaptation live outside.

Each step records Eq. (3). U proposes, C checks actual tool receipts, and the
fixed K commits. Only JSON memory data can evolve; the kernel never self-edits.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
import math
import re
import shlex
import time
from typing import Any, Protocol
from uuid import uuid4

from .client import ModelClientError, ModelDeadlineExceeded, ModelReply
from .memory import invoke, load_memory, memory_digest, unresolved_signature, validate_memory
from .prompts import ACTOR, INITIALIZE, UPDATE
from .protocol import ProtocolError, parse_action, parse_object
from .working import apply_proposal, initialize, invalidate_completions, verifier_digest


class Terminal(Protocol):
    def observe(self) -> str: ...
    def execute(self, keystrokes: str, duration: float) -> str: ...


@dataclass(frozen=True)
class RecurisConfig:
    max_steps: int = 200
    max_tool_calls: int = 400
    max_model_calls: int = 450
    max_total_seconds: float = 3600
    max_context_chars: int = 120000
    max_observation_chars: int = 20000
    max_command_duration: float = 120
    max_verify_seconds: float = 120
    max_parse_attempts: int = 2
    max_consecutive_tool_errors: int = 10
    history_turns: int = 12

    def __post_init__(self):
        for key in ("max_steps", "max_tool_calls", "max_model_calls", "max_context_chars",
                    "max_observation_chars", "max_parse_attempts", "max_consecutive_tool_errors", "history_turns"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f"{key} must be a positive integer")
        for key in ("max_total_seconds", "max_command_duration", "max_verify_seconds"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 86400 or not math.isfinite(value):
                raise ValueError(f"{key} must be finite and in (0,86400]")
        if self.max_context_chars < 12000 or self.max_observation_chars > self.max_context_chars // 2:
            raise ValueError("Context must be >=12000 chars and observation <= half the context")


@dataclass
class RunResult:
    stop_reason: str = ""
    final_answer: str = ""
    memory_digest: str = ""
    working_state: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    steps: int = 0
    elapsed_seconds: float = 0
    error: str | None = None
    error_phase: str | None = None
    official_success: None = None


class _Stopped(Exception):
    pass


def clip(text: str, limit: int) -> str:
    if not isinstance(text, str):
        raise TypeError("Expected terminal text")
    if len(text) <= limit:
        return text
    marker = f"\n[TRUNCATED: {len(text)} original chars, middle omitted]\n"
    if limit <= len(marker):
        return "[TRUNCATED]"[:max(0, limit)]
    remaining = limit - len(marker)
    return text[:remaining // 2] + marker + text[-(remaining - remaining // 2):]


def verification_keystrokes(command: str, nonce: str) -> str:
    # Arbitrary task checks execute only inside the provided container session.
    # Child bash isolates `exit`/`exec` in a verifier from the parent receipt print.
    status_var = "__recuris_rc_" + nonce[:12]
    return ("printf '\\n__RECURIS_BEGIN_" + nonce + "__\\n'; command bash -c " + shlex.quote(command) + "; " + status_var + "=$?; "
            + "printf '\\n__RECURIS_" + nonce + "__=%s\\n' \"$" + status_var + "\"\n")


def parse_exit_receipt(output: str, nonce: str) -> int | None:
    clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output).replace("\r", "")
    matches = re.findall(r"(?m)^__RECURIS_" + re.escape(nonce) + r"__=(\d{1,3})[ \t]*$", clean)
    # Ambiguous receipts are not completion evidence.
    starts = list(re.finditer(r"(?m)^__RECURIS_BEGIN_" + re.escape(nonce) + r"__[ \t]*$", clean))
    ends = list(re.finditer(r"(?m)^__RECURIS_" + re.escape(nonce) + r"__=\d{1,3}[ \t]*$", clean))
    if len(starts) != 1 or len(ends) != 1 or starts[0].end() >= ends[0].start():
        return None
    if len(matches) != 1 or not 0 <= int(matches[0]) <= 255:
        return None
    return int(matches[0])


class RecurisRunner:
    def __init__(self, client: Any, config: RecurisConfig | None = None,
                 memory: dict | None = None, logger: Any = None):
        self.client = client
        self.config = config or RecurisConfig()
        self.memory = validate_memory(memory) if memory is not None else load_memory()
        self.logger = logger

    def _log(self, event, **data):
        if self.logger is not None:
            self.logger.write(event, **data)

    def _time(self):
        if time.monotonic() >= self._deadline:
            raise _Stopped("max_total_seconds_reached")

    @staticmethod
    def _size(messages):
        return sum(len(m["content"]) + 30 for m in messages)

    def _complete(self, messages, purpose):
        self._time()
        if self._result.model_calls >= self.config.max_model_calls:
            raise _Stopped("max_model_calls_reached")
        if self._size(messages) > self.config.max_context_chars:
            raise _Stopped("max_context_chars_reached")
        self._result.model_calls += 1
        self._log("model_request", purpose=purpose, messages=messages)
        try:
            reply = self.client.complete(messages, purpose=purpose, deadline_monotonic=self._deadline)
        except ModelClientError as exc:
            self._result.input_tokens += exc.input_tokens
            self._result.output_tokens += exc.output_tokens
            if isinstance(exc, ModelDeadlineExceeded):
                raise _Stopped("max_total_seconds_reached") from exc
            raise
        self._result.input_tokens += reply.input_tokens
        self._result.output_tokens += reply.output_tokens
        self._log("model_response", purpose=purpose, content=reply.content,
                  input_tokens=reply.input_tokens, output_tokens=reply.output_tokens, finish_reason=reply.finish_reason)
        self._time()
        return reply

    def _json(self, messages, purpose, validate):
        base = messages
        for index in range(self.config.max_parse_attempts):
            reply = self._complete(messages, purpose)
            try:
                if reply.finish_reason == "length":
                    raise ProtocolError("Truncated generation; return shorter complete JSON")
                return validate(reply.content)
            except (ProtocolError, KeyError, TypeError) as exc:
                self._log("invalid_response", purpose=purpose, error=str(exc), attempt=index + 1)
                if index + 1 == self.config.max_parse_attempts:
                    raise ProtocolError(str(exc)) from exc
                messages = [*base, {"role": "user", "content": f"Protocol error: {exc}. Regenerate valid JSON; no proposed actions/state changes were applied."}]
        raise AssertionError("unreachable")

    def _terminal(self, terminal, keys, duration):
        self._time()
        if self._result.tool_calls >= self.config.max_tool_calls:
            raise _Stopped("max_tool_calls_reached")
        self._phase = "terminal"
        self._result.tool_calls += 1
        wait = min(duration, self.config.max_command_duration, max(0, self._deadline - time.monotonic()))
        self._log("terminal_input", keystrokes=keys, duration=wait, tool_call=self._result.tool_calls)
        output = terminal.execute(keys, wait)
        if not isinstance(output, str):
            raise TypeError("Terminal observation must be text")
        self._log("terminal_output", observation=output, tool_call=self._result.tool_calls)
        self._time()
        return output

    def _check_observation(self, output):
        pending = self._pending_check
        pending["output"] += output
        # tmux incremental chunks may join immediately before the marker.
        code = parse_exit_receipt(pending["output"], pending["nonce"])
        actual_output = pending["output"]
        if code is not None:
            clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", actual_output).replace("\r", "")
            begin = re.search(r"(?m)^__RECURIS_BEGIN_" + re.escape(pending["nonce"]) + r"__[ \t]*$", clean)
            end = re.search(r"(?m)^__RECURIS_" + re.escape(pending["nonce"]) + r"__=\d{1,3}[ \t]*$", clean)
            actual_output = clean[begin.end():end.start()].strip("\n")
        return {"kind": "verification", "goal_id": pending["goal_id"],
                "verification_digest": pending["verification_digest"], "revision": pending["revision"],
                "output": actual_output, "completed": code is not None,
                "exit_code": code, "synthetic": False}

    def _verify(self, terminal, goal, duration):
        if self._pending_check is not None:
            return {"kind": "rejected_action", "output": "A verification is still running; poll with execute keystrokes='' or interrupt it.", "synthetic": True}
        nonce = uuid4().hex
        self._pending_check = {"nonce": nonce, "goal_id": goal["id"], "output": "",
                               "verification_digest": verifier_digest(goal["verification"]), "revision": self._revision}
        until = min(self._deadline, time.monotonic() + self.config.max_verify_seconds)
        output = self._terminal(terminal, verification_keystrokes(goal["verification"]["command"], nonce), min(duration, self.config.max_verify_seconds))
        observation = self._check_observation(output)
        while not observation["completed"] and time.monotonic() < until:
            self._time()
            output = self._terminal(terminal, "", min(1.0, max(0, until - time.monotonic())))
            observation = self._check_observation(output)
        if observation["completed"]:
            self._pending_check = None
        return observation

    def _execute(self, terminal, action):
        keys = action["keystrokes"]
        if self._pending_check is not None and keys not in {"", "C-c"}:
            return {"kind": "rejected_action", "output": "Verifier still running. Poll or interrupt before another command.", "synthetic": True}
        # Even a read-looking command can mutate files. Polls alone do not.
        if keys:
            self._revision += 1
            self._state = invalidate_completions(self._state)
        output = self._terminal(terminal, keys, action["duration"])
        if self._pending_check is not None and keys == "":
            observation = self._check_observation(output)
            if observation["completed"]:
                self._pending_check = None
            return observation
        if keys == "C-c":
            self._pending_check = None
        return {"kind": "terminal", "output": output, "revision": self._revision, "synthetic": False}

    def _visible_receipt(self, receipt):
        value = deepcopy(receipt)
        full = value.get("output", "")
        value["output"] = clip(full, self.config.max_observation_chars)
        value["output_truncated"] = len(full) > self.config.max_observation_chars
        return value

    def _actor_messages(self, instruction, initial, history, active_skills):
        context = {"task": instruction, "working_state": self._state, "delivered_skills": active_skills,
                   "initial_terminal_observation": clip(initial, self.config.max_observation_chars),
                   "max_command_duration": self.config.max_command_duration,
                   "environment_revision": self._revision, "verification_pending": self._pending_check is not None}
        fixed = [{"role": "system", "content": ACTOR},
                 {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
        tail = history[-2 * self.config.history_turns:]
        # Preserve the task, current WM and delivered skills; drop oldest complete
        # action/observation pairs before overflowing. The full trace stays on disk.
        while tail and self._size(fixed + tail) > self.config.max_context_chars - 3000:
            tail = tail[2:]
        if len(tail) < len(history):
            fixed[1]["content"] += "\n[Older dialogue omitted; use current verified WM. Full execution remains in the structured trace.]"
        return fixed + tail

    def run(self, instruction: str, terminal: Terminal) -> RunResult:
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("instruction must be nonempty")
        started = time.monotonic()
        self._deadline = started + self.config.max_total_seconds
        self._result = RunResult(memory_digest=memory_digest(self.memory))
        self._state, self._receipts = [], {}
        self._pending_check = None
        self._revision = 0
        self._phase = "initialization"
        history, active_skills = [], []
        previous_unresolved = None
        errors = 0
        context = {"instruction": instruction, "memory_digest": self._result.memory_digest}
        self._log("run_start", **context, config=asdict(self.config))
        if self.logger is not None:
            self.logger.save("context.json", context)
            self.logger.save("memory.json", self.memory)
        try:
            self._phase = "terminal"
            self._time()
            initial = terminal.observe()
            self._log("initial_observation", observation=initial)
            self._time()
            self._phase = "initialization"
            messages = [{"role": "system", "content": INITIALIZE}, {"role": "user", "content": json.dumps({
                "task": instruction, "initial_observation": clip(initial, self.config.max_observation_chars), "W": self.memory["W"]}, ensure_ascii=False)}]
            self._state = self._json(messages, "initialize", lambda text: initialize(parse_object(text), self.memory["W"]["max_goals"]))
            for step in range(1, self.config.max_steps + 1):
                self._time()
                self._result.steps = step
                before = deepcopy(self._state)
                selected = invoke(self.memory, self._state, step, previous_unresolved)
                previous_unresolved = unresolved_signature(self._state)
                if selected:
                    active_skills = selected
                self._phase = "actor"
                action = self._json(self._actor_messages(instruction, initial, history, active_skills), "act",
                                    lambda text: parse_action(text, self.config.max_command_duration))
                entry = {"step_id": step, "event": "turn", "state_before": before,
                         "invoked_skills": [s["id"] for s in selected], "action": action,
                         "observation": {}, "proposed_state": {}, "checker_decisions": [], "state_after": deepcopy(self._state)}
                self._result.trace.append(entry)
                if action["operation"] in {"finish", "stop"}:
                    completed = bool(self._state) and all(g["status"] == "done" for g in self._state) and self._pending_check is None
                    if action["operation"] == "stop" or completed:
                        self._result.final_answer = action["final_answer"]
                        self._result.stop_reason = "task_complete" if completed else "actor_stopped_incomplete"
                        entry["observation"] = {"kind": "completion_request", "accepted": True, "synthetic": True}
                        self._log("trace_step", trace=entry)
                        break
                    observation = {"kind": "rejected_completion", "output": "Unverified goals remain. Execute meaningful checks for every goal, or use stop to report incomplete work.", "synthetic": True}
                elif action["operation"] == "verify":
                    goal = next((g for g in self._state if g["id"] == action["goal_id"]), None)
                    if goal is None:
                        observation = {"kind": "rejected_action", "output": "Unknown goal_id. Use an existing WM goal.", "synthetic": True}
                    else:
                        observation = self._verify(terminal, goal, action["duration"])
                else:
                    observation = self._execute(terminal, action)
                observation["id"] = f"receipt-{step}"
                self._receipts[observation["id"]] = deepcopy(observation)
                visible = self._visible_receipt(observation)
                entry["observation"] = visible
                errors = errors + 1 if (observation.get("completed") and observation.get("exit_code") != 0) else 0
                if errors >= self.config.max_consecutive_tool_errors:
                    entry["state_after"] = deepcopy(self._state)
                    self._result.stop_reason = "max_consecutive_tool_errors_reached"
                    self._log("trace_step", trace=entry)
                    break
                self._phase = "working_memory"
                update_messages = [{"role": "system", "content": UPDATE}, {"role": "user", "content": json.dumps({
                    "task": instruction, "W": self.memory["W"], "current_state": self._state,
                    "action": action, "observation": visible}, ensure_ascii=False)}]
                def validate_update(text):
                    proposal = parse_object(text)
                    state, decisions = apply_proposal(self._state, proposal, self._receipts, self._revision, self.memory)
                    return proposal, state, decisions
                proposal, self._state, decisions = self._json(update_messages, "update", validate_update)
                entry.update(proposed_state=proposal, checker_decisions=decisions, state_after=deepcopy(self._state))
                self._log("trace_step", trace=entry)
                history.extend([{"role": "assistant", "content": json.dumps(action, ensure_ascii=False)},
                                {"role": "user", "content": json.dumps({"observation": visible, "checker_decisions": decisions}, ensure_ascii=False)}])
                if self.logger is not None:
                    self.logger.save("trace.json", self._result.trace)
            else:
                self._result.stop_reason = "max_steps_reached"
        except _Stopped as exc:
            self._result.stop_reason = str(exc)
        except ProtocolError as exc:
            self._result.stop_reason = "protocol_error"
            self._result.error = str(exc)
            self._result.error_phase = self._phase
        except Exception as exc:
            self._result.stop_reason = "model_error" if isinstance(exc, ModelClientError) else f"{self._phase}_error"
            self._result.error = f"{type(exc).__name__}: {exc}"
            self._result.error_phase = self._phase
        finally:
            self._result.working_state = deepcopy(self._state)
            self._result.elapsed_seconds = time.monotonic() - started
            self._log("run_end", result=asdict(self._result))
            if self.logger is not None:
                self.logger.save("trace.json", self._result.trace)
                self.logger.save("result.json", self._result)
        return self._result
