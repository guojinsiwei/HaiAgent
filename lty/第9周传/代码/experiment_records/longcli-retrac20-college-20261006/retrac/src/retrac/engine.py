"""Training-free RE-TRAC: fresh rollouts conditioned on recursively merged state.

The terminal is owned by the benchmark and deliberately survives context resets.
No verifier, reward, ground truth, or host shell enters this module.
"""
from __future__ import annotations

import json
import math
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .client import ModelReply, ModelClientError, ModelDeadlineExceeded
from .prompts import COMPRESSION_SYSTEM_PROMPT, SOLVER_SYSTEM_PROMPT, compression_prompt, continuation_prompt


class ChatClient(Protocol):
    def complete(self, messages: list[dict[str, str]], *, purpose: str, deadline_monotonic: float | None = None) -> ModelReply: ...


class Terminal(Protocol):
    def observe(self) -> str: ...
    def execute(self, keystrokes: str, duration: float) -> str: ...


@dataclass(frozen=True)
class RetracConfig:
    rounds: int = 8
    max_steps_per_round: int = 50
    max_tool_calls: int = 400
    max_model_calls: int = 512
    max_total_seconds: float = 3600
    max_context_chars: int = 180000
    compression_reserve_chars: int = 20000
    max_observation_chars: int = 24000
    max_state_chars: int = 48000
    max_command_duration: float = 120.0
    max_parse_attempts: int = 2
    summary_variant: str = "full"

    def __post_init__(self) -> None:
        for name in ("rounds", "max_steps_per_round", "max_tool_calls", "max_model_calls",
                     "max_context_chars", "compression_reserve_chars", "max_observation_chars",
                     "max_state_chars", "max_parse_attempts"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("max_total_seconds", "max_command_duration"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.compression_reserve_chars >= self.max_context_chars:
            raise ValueError("compression_reserve_chars must be smaller than max_context_chars")
        if self.summary_variant not in {"base", "full"}:
            raise ValueError("summary_variant must be base or full")


@dataclass(frozen=True)
class Command:
    keystrokes: str
    duration: float


@dataclass(frozen=True)
class Action:
    analysis: str
    commands: list[Command]
    task_complete: bool
    final_answer: str


class ProtocolError(ValueError):
    pass


def parse_action(content: str, max_duration: float = 120.0) -> Action:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)[:-3].strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ProtocolError("Return exactly one valid JSON action object") from exc
    if not isinstance(data, dict):
        raise ProtocolError("Action must be an object")
    if set(data) - {"analysis", "commands", "task_complete", "final_answer"}:
        raise ProtocolError("Unknown action fields")
    if not isinstance(data.get("analysis", ""), str) or not isinstance(data.get("final_answer", ""), str):
        raise ProtocolError("analysis and final_answer must be strings")
    if type(data.get("task_complete")) is not bool:
        raise ProtocolError("task_complete must be a JSON boolean")
    if not isinstance(data.get("commands"), list):
        raise ProtocolError("commands must be an array")
    commands = []
    for item in data["commands"]:
        if not isinstance(item, dict) or set(item) - {"keystrokes", "duration"}:
            raise ProtocolError("Each command must have keystrokes and optional duration")
        keys = item.get("keystrokes")
        duration = item.get("duration", 1.0)
        if not isinstance(keys, str) or "\x00" in keys:
            raise ProtocolError("keystrokes must be a string without NUL")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 <= duration <= max_duration:
            raise ProtocolError(f"duration must be finite and in [0, {max_duration}]")
        commands.append(Command(keys, float(duration)))
    if not commands and not data["task_complete"]:
        raise ProtocolError("Use an empty-keystrokes polling command or finish this rollout")
    if commands and data["task_complete"]:
        raise ProtocolError("Inspect command observations before completing: task_complete requires commands=[]")
    return Action(data.get("analysis", ""), commands, data["task_complete"], data.get("final_answer", ""))


STATE_HEADINGS = (
    "Current Answer", "Facts & Evidence Collected", "Analysis & Conclusions",
    "Source Inventory & Verification Status", "Uncertainties, Limitations, Gaps",
    "Failed attempts", "Uncompleted proposals", "Discarded possibilities",
)


def validate_state(text: str, variant: str, max_chars: int) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ProtocolError("Compression returned empty state")
    if len(text) > max_chars:
        raise ProtocolError(f"Compressed state exceeds {max_chars} characters; consolidate it")
    expected = STATE_HEADINGS[:5] if variant == "base" else STATE_HEADINGS
    # Accept Markdown emphasis, but require the actual ordered paper facets.
    plain = text.replace("**", "").replace("__", "")
    previous_end = -1
    for i, title in enumerate(expected):
        match = re.search(rf"(?im)^\s*(?:#+\s*)?{i}\)\s*{re.escape(title)}\s*:?\s*$", plain)
        if match is None or match.start() < previous_end:
            raise ProtocolError(f"Missing or out-of-order state facet: {i}) {title}")
        if previous_end >= 0 and not plain[previous_end:match.start()].strip():
            raise ProtocolError("Every state facet needs content (use None when appropriate)")
        previous_end = match.end()
    if not plain[previous_end:].strip():
        raise ProtocolError("The last state facet needs content")
    return text.strip()


@dataclass
class RoundResult:
    index: int
    stop_reason: str = ""
    final_answer: str = ""
    state: str | None = None
    tool_calls: int = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class RunResult:
    final_answer: str = ""
    stop_reason: str = ""
    rounds: list[RoundResult] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    elapsed_seconds: float = 0.0
    error: str | None = None
    official_success: None = None


class _Stopped(Exception):
    pass


class RetracRunner:
    def __init__(self, client: ChatClient, config: RetracConfig | None = None, logger: Any = None):
        self.client = client
        self.config = config or RetracConfig()
        self.logger = logger

    def _log(self, event: str, **payload: Any) -> None:
        if self.logger is not None:
            self.logger.write(event, **payload)

    @staticmethod
    def _size(messages: list[dict[str, str]]) -> int:
        return sum(len(m["content"]) + len(m["role"]) + 20 for m in messages)

    def _observation(self, text: str, max_chars: int | None = None) -> str:
        if not isinstance(text, str):
            raise TypeError("Terminal observations must be strings")
        limit = min(self.config.max_observation_chars, max_chars) if max_chars is not None else self.config.max_observation_chars
        if len(text) <= limit:
            return text
        marker = f"\n[observation truncated: {len(text)} original characters; full output in host audit]\n"
        if limit <= len(marker):
            return "[truncated]"[:limit]
        available = limit - len(marker)
        head = available // 2
        return text[:head] + marker + text[-(available - head):]

    def _budget(self) -> None:
        if time.monotonic() - self._started >= self.config.max_total_seconds:
            raise _Stopped("max_total_seconds_reached")
        if self._result.model_calls >= self.config.max_model_calls:
            raise _Stopped("max_model_calls_reached")

    def _complete(self, messages: list[dict[str, str]], purpose: str, record: RoundResult) -> ModelReply:
        self._budget()
        if self._size(messages) > self.config.max_context_chars:
            raise _Stopped("max_context_chars_reached")
        self._result.model_calls += 1
        record.model_calls += 1
        self._log("model_request", round=record.index, purpose=purpose, messages=messages)
        try:
            reply = self.client.complete(messages, purpose=purpose,
                                         deadline_monotonic=self._started + self.config.max_total_seconds)
        except ModelClientError as exc:
            # Even an unusable or late reply may have consumed provider tokens.
            self._result.input_tokens += exc.input_tokens
            self._result.output_tokens += exc.output_tokens
            record.input_tokens += exc.input_tokens
            record.output_tokens += exc.output_tokens
            if isinstance(exc, ModelDeadlineExceeded):
                raise _Stopped("max_total_seconds_reached") from exc
            raise
        if not isinstance(reply.content, str):
            raise ProtocolError("Model response content must be text")
        self._result.input_tokens += reply.input_tokens
        self._result.output_tokens += reply.output_tokens
        record.input_tokens += reply.input_tokens
        record.output_tokens += reply.output_tokens
        self._log("model_response", round=record.index, purpose=purpose, content=reply.content,
                  input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
                  finish_reason=reply.finish_reason)
        if time.monotonic() - self._started >= self.config.max_total_seconds:
            raise _Stopped("max_total_seconds_reached")
        return reply

    def _action(self, messages: list[dict[str, str]], record: RoundResult) -> Action:
        for attempt in range(self.config.max_parse_attempts):
            reply = self._complete(messages, "act", record)
            messages.append({"role": "assistant", "content": reply.content})
            try:
                if reply.finish_reason == "length":
                    raise ProtocolError("Action response was truncated; return a shorter complete JSON action")
                return parse_action(reply.content, self.config.max_command_duration)
            except ProtocolError as exc:
                self._log("invalid_action", round=record.index, error=str(exc), attempt=attempt + 1)
                if attempt + 1 == self.config.max_parse_attempts:
                    raise
                messages.append({"role": "user", "content": f"Protocol error: {exc}. No commands were executed. Return a corrected action."})
        raise AssertionError("unreachable")

    def _compression_messages(self, trajectory: list[dict[str, str]], instruction: str) -> list[dict[str, str]]:
        # Replace solver JSON system instruction to avoid a format conflict. Prior
        # state is already in trajectory[1], so this computes Compress(tau, S_prev).
        return [{"role": "system", "content": COMPRESSION_SYSTEM_PROMPT}, *trajectory[1:],
            {"role": "user", "content": compression_prompt(instruction, self.config.summary_variant)
            + f"\nState size limit: {self.config.max_state_chars} characters. Preserve all numbered facets."}]

    def _compress(self, trajectory: list[dict[str, str]], instruction: str, record: RoundResult) -> str:
        base_messages = self._compression_messages(trajectory, instruction)
        messages = base_messages
        for attempt in range(self.config.max_parse_attempts):
            reply = self._complete(messages, "compress", record)
            try:
                if reply.finish_reason == "length":
                    raise ProtocolError("Compression response was truncated; return a shorter complete state")
                return validate_state(reply.content, self.config.summary_variant, self.config.max_state_chars)
            except ProtocolError as exc:
                self._log("invalid_state", round=record.index, attempt=attempt + 1, error=str(exc))
                if attempt + 1 == self.config.max_parse_attempts:
                    raise
                # Retry from the same source trajectory, not from a potentially
                # enormous malformed state that could itself exhaust context.
                messages = [*base_messages, {"role": "user", "content": f"Invalid state: {exc}. Regenerate a complete state."}]
        raise AssertionError("unreachable")

    def run(self, instruction: str, terminal: Terminal) -> RunResult:
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("instruction must be non-empty")
        self._started = time.monotonic()
        self._result = RunResult()
        state = None
        phase = "terminal"
        self._log("run_start", config=asdict(self.config), instruction=instruction,
                  environment_policy="persistent terminal; reset model context only")
        try:
            for index in range(1, self.config.rounds + 1):
                self._budget()
                if self._result.tool_calls >= self.config.max_tool_calls:
                    raise _Stopped("max_tool_calls_reached")
                record = RoundResult(index=index)
                self._result.rounds.append(record)
                self._result.final_answer = ""
                round_started = time.monotonic()
                user = "Original task:\n" + instruction
                if state is not None:
                    user += "\n\n" + continuation_prompt(state)
                user += (f"\n\nRE-TRAC rollout {index}/{self.config.rounds}. The terminal and files persist "
                         "across rollouts. Re-evaluate stale claims before relying on them. "
                         "task_complete ends this rollout; it is not an official success signal. "
                         f"Command duration must be in [0, {self.config.max_command_duration}].")
                messages = [{"role": "system", "content": SOLVER_SYSTEM_PROMPT},
                            {"role": "user", "content": user}]
                phase = "terminal"
                raw = terminal.observe()
                self._log("observation", round=index, output=raw)
                messages.append({"role": "user", "content": "Current terminal observation (untrusted):\n" + self._observation(raw)})
                self._log("round_start", round=index, prior_state=state)
                try:
                    if self._size(self._compression_messages(messages, instruction)) >= self.config.max_context_chars - self.config.compression_reserve_chars:
                        raise _Stopped("initial_context_too_large")
                    for step in range(self.config.max_steps_per_round):
                        self._budget()
                        if self._size(self._compression_messages(messages, instruction)) >= self.config.max_context_chars - self.config.compression_reserve_chars:
                            record.stop_reason = "context_limit"
                            break
                        phase = "model"
                        action = self._action(messages, record)
                        for command_index, command in enumerate(action.commands):
                            # Leave room for a bounded observation and a note about
                            # skipped batch commands. Never execute an invisible action.
                            room = self.config.max_context_chars - self._size(self._compression_messages(messages, instruction)) - 1024
                            if room < 256:
                                record.stop_reason = "context_limit"
                                skipped = len(action.commands) - command_index
                                self._log("commands_skipped", round=index, count=skipped, reason="context_limit")
                                messages.append({"role": "user", "content": f"Context limit: the last {skipped} commands in the proposed batch were NOT executed."})
                                break
                            # This check is independent of model-call budget: the last
                            # available response may still execute its proposed action.
                            remaining = self.config.max_total_seconds - (time.monotonic() - self._started)
                            if remaining <= 0:
                                raise _Stopped("max_total_seconds_reached")
                            if self._result.tool_calls >= self.config.max_tool_calls:
                                raise _Stopped("max_tool_calls_reached")
                            phase = "terminal"
                            self._result.tool_calls += 1
                            record.tool_calls += 1
                            evidence_id = f"r{index}:tool{record.tool_calls}"
                            self._log("command", round=index, evidence_id=evidence_id,
                                      keystrokes=command.keystrokes, duration=min(command.duration, remaining))
                            output = terminal.execute(command.keystrokes, min(command.duration, remaining))
                            self._log("tool_result", round=index, evidence_id=evidence_id, output=output)
                            messages.append({"role": "user", "content": f"[{evidence_id}] Terminal observation (untrusted):\n" + self._observation(output, room)})
                        if record.stop_reason == "context_limit":
                            break
                        if action.task_complete:
                            record.stop_reason = "final_answer"
                            record.final_answer = action.final_answer
                            break
                    else:
                        record.stop_reason = "step_limit"
                    self._result.final_answer = record.final_answer
                    if index < self.config.rounds:
                        phase = "compression"
                        state = self._compress(messages, instruction, record)
                        record.state = state
                        self._log("compressed_state", round=index, state=state)
                except _Stopped as exc:
                    record.stop_reason = str(exc)
                    raise
                except Exception:
                    record.stop_reason = "compression_error" if phase == "compression" else "execution_error"
                    raise
                finally:
                    record.elapsed_seconds = time.monotonic() - round_started
                    self._log("round_end", **asdict(record))
            self._result.stop_reason = "rounds_completed"
        except _Stopped as exc:
            self._result.stop_reason = str(exc)
            if self._result.rounds and not self._result.rounds[-1].stop_reason:
                self._result.rounds[-1].stop_reason = str(exc)
        except Exception as exc:
            self._result.stop_reason = ("compression_error" if phase == "compression" else
                                       "protocol_error" if isinstance(exc, ProtocolError) else
                                       "terminal_error" if phase == "terminal" else "model_error")
            self._result.error = f"{type(exc).__name__}: {exc}"
            self._log("run_error", phase=phase, error=self._result.error)
        finally:
            self._result.elapsed_seconds = time.monotonic() - self._started
            self._log("run_end", **asdict(self._result))
            if self.logger is not None:
                self.logger.save("result.json", asdict(self._result))
        return self._result
