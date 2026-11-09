"""Reflexion: act -> evaluate -> reflect on failure -> bounded memory -> retry.

The terminal environment persists. Only the Actor's short-term conversation is
reset between trials; this is an explicit LongCLI adaptation of the paper.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import json
import math
import time
from typing import Any, Protocol

from .client import ModelClientError, ModelDeadlineExceeded, ModelReply
from .prompts import ACTOR_SYSTEM, EVALUATOR_SYSTEM, REFLECTION_SYSTEM, trial_prompt
from .protocol import Action, Evaluation, ProtocolError, parse_action, parse_evaluation, response_text


class ChatClient(Protocol):
    def complete(self, messages: list[dict[str, str]], *, purpose: str,
                 deadline_monotonic: float | None = None) -> ModelReply: ...


class Terminal(Protocol):
    def observe(self) -> str: ...
    def execute(self, keystrokes: str, duration: float) -> str: ...


@dataclass(frozen=True)
class ReflexionConfig:
    max_trials: int = 3
    memory_size: int = 3
    max_steps_per_trial: int = 40
    max_tool_calls: int = 120
    max_model_calls: int = 256
    max_total_seconds: float = 3600
    max_context_chars: int = 120000
    context_reserve_chars: int = 16000
    max_observation_chars: int = 16000
    max_reflection_chars: int = 4000
    max_command_duration: float = 120
    max_parse_attempts: int = 2
    repeat_action_limit: int = 4

    def __post_init__(self):
        integer_fields = (
            "max_trials", "memory_size", "max_steps_per_trial", "max_tool_calls",
            "max_model_calls", "max_context_chars", "context_reserve_chars",
            "max_observation_chars", "max_reflection_chars", "max_parse_attempts",
            "repeat_action_limit",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("max_total_seconds", "max_command_duration"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.context_reserve_chars < 4000:
            raise ValueError("context_reserve_chars must be at least 4000")
        if self.max_context_chars < self.context_reserve_chars + 4000:
            raise ValueError("max_context_chars must leave at least 4000 characters beyond the reserve")
        if self.memory_size * self.max_reflection_chars > self.max_context_chars - self.context_reserve_chars - 4000:
            raise ValueError("Reflection memory is too large for the configured context")


@dataclass
class TrialResult:
    index: int
    stop_reason: str = ""
    final_answer: str = ""
    evaluation: Evaluation | None = None
    reflection: str | None = None
    memory_before: list[str] = field(default_factory=list)
    actor_steps: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_seconds: float = 0


@dataclass
class RunResult:
    final_answer: str = ""
    stop_reason: str = ""
    trials: list[TrialResult] = field(default_factory=list)
    memory: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    elapsed_seconds: float = 0
    error: str | None = None
    error_phase: str | None = None
    official_success: None = None
    environment_policy: str = "persistent_terminal_and_filesystem"


class _Stopped(Exception):
    pass


def clip_text(text: str, limit: int) -> str:
    """Head/tail truncation with an explicit omission marker; not compression."""
    if not isinstance(text, str):
        raise TypeError("Terminal observations and review evidence must be strings")
    if len(text) <= limit:
        return text
    marker = f"\n[TRUNCATED: {len(text)} original characters; middle omitted]\n"
    if limit <= len(marker):
        return "[TRUNCATED]"[:max(0, limit)]
    remaining = limit - len(marker)
    head = remaining // 2
    return text[:head] + marker + text[-(remaining - head):]


class ReflexionRunner:
    def __init__(self, client: ChatClient, config: ReflexionConfig | None = None,
                 logger: Any = None):
        self.client = client
        self.config = config or ReflexionConfig()
        self.logger = logger

    def _log(self, event: str, **payload: Any):
        if self.logger is not None:
            self.logger.write(event, **payload)

    @staticmethod
    def _size(messages: list[dict[str, str]]) -> int:
        return sum(len(m["content"]) + len(m["role"]) + 20 for m in messages)

    def _time_budget(self):
        if time.monotonic() >= self._deadline:
            raise _Stopped("max_total_seconds_reached")

    def _retry_budget(self):
        self._time_budget()
        if self._result.tool_calls >= self.config.max_tool_calls:
            raise _Stopped("max_tool_calls_reached")
        if self._result.model_calls >= self.config.max_model_calls:
            raise _Stopped("max_model_calls_reached")

    def _usage(self, record: TrialResult, reply: ModelReply | ModelClientError):
        for name in ("input_tokens", "output_tokens"):
            value = getattr(reply, name)
            setattr(self._result, name, getattr(self._result, name) + value)
            setattr(record, name, getattr(record, name) + value)

    def _complete(self, messages: list[dict[str, str]], purpose: str,
                  record: TrialResult) -> ModelReply:
        self._time_budget()
        if self._result.model_calls >= self.config.max_model_calls:
            raise _Stopped("max_model_calls_reached")
        if self._size(messages) > self.config.max_context_chars:
            raise _Stopped("max_context_chars_reached")
        self._result.model_calls += 1
        record.model_calls += 1
        self._log("model_request", trial=record.index, purpose=purpose, messages=messages)
        try:
            reply = self.client.complete(messages, purpose=purpose,
                                         deadline_monotonic=self._deadline)
        except ModelClientError as exc:
            self._usage(record, exc)
            if isinstance(exc, ModelDeadlineExceeded):
                raise _Stopped("max_total_seconds_reached") from exc
            raise
        self._usage(record, reply)
        self._log("model_response", trial=record.index, purpose=purpose, content=reply.content,
                  input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
                  finish_reason=reply.finish_reason)
        self._time_budget()
        if not isinstance(reply.content, str):
            raise ProtocolError("Model response content must be text")
        return reply

    def _action(self, messages: list[dict[str, str]], record: TrialResult) -> Action:
        for attempt in range(self.config.max_parse_attempts):
            reply = self._complete(messages, "act", record)
            try:
                if reply.finish_reason == "length":
                    raise ProtocolError("Action was truncated; return a shorter complete JSON object")
                action = parse_action(reply.content, self.config.max_command_duration)
            except ProtocolError as exc:
                self._log("invalid_action", trial=record.index, error=str(exc), attempt=attempt + 1)
                if attempt + 1 == self.config.max_parse_attempts:
                    raise
                # Do not replay possibly enormous invalid output into the next prompt.
                messages.append({"role": "user", "content": f"Invalid action: {exc}. No commands were executed. Return corrected JSON."})
            else:
                messages.append({"role": "assistant", "content": reply.content})
                return action
        raise AssertionError("unreachable")

    def _review_messages(self, system: str, instruction: str, memory: list[str],
                         trajectory: list[dict[str, str]], record: TrialResult,
                         purpose: str) -> list[dict[str, str]]:
        metadata = {
            "task": instruction, "previous_reflections": memory,
            "trial": record.index, "actor_stop_reason": record.stop_reason,
            "evaluation": asdict(record.evaluation) if record.evaluation else None,
            "reflection_character_limit": self.config.max_reflection_chars,
            "environment": "same terminal/filesystem; no environment reset",
            "evidence_rule": "Only observation messages demonstrate execution. Commands in Actor messages without corresponding observations are unexecuted proposals.",
        }
        prefix = json.dumps(metadata, ensure_ascii=False) + "\n\nCURRENT TRIAL TRAJECTORY:\n"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prefix}]
        # Leave room for format-repair feedback; task and memory are never silently clipped.
        available = self.config.max_context_chars - self._size(messages) - 2000
        if available < 1000:
            raise _Stopped("max_context_chars_reached")
        serialized = json.dumps(trajectory, ensure_ascii=False)
        evidence = clip_text(serialized, available)
        if len(serialized) > available:
            self._log("review_evidence_truncated", trial=record.index, purpose=purpose,
                      original_chars=len(serialized), included_chars=len(evidence))
        messages[1]["content"] += evidence
        return messages

    def _evaluate(self, instruction, memory, trajectory, record) -> Evaluation:
        if record.stop_reason != "actor_complete":
            # Paper §4.1 also uses a deterministic failure evaluator for loops/limits.
            return Evaluation(False,
                f"Trial stopped before verified completion: {record.stop_reason}. Diagnose the incomplete work and change strategy.",
                [f"Actor stopped after {record.actor_steps} responses and {record.tool_calls} terminal calls."],
                source="failure_heuristic")
        base = self._review_messages(EVALUATOR_SYSTEM, instruction, memory, trajectory, record, "evaluate")
        messages = base
        for attempt in range(self.config.max_parse_attempts):
            reply = self._complete(messages, "evaluate", record)
            try:
                if reply.finish_reason == "length":
                    raise ProtocolError("Evaluation was truncated")
                return parse_evaluation(reply.content)
            except ProtocolError as exc:
                self._log("invalid_evaluation", trial=record.index, attempt=attempt + 1, error=str(exc))
                if attempt + 1 == self.config.max_parse_attempts:
                    raise
                messages = [*base, {"role": "user", "content": f"Invalid evaluation: {exc}. Return corrected evaluation JSON."}]
        raise AssertionError("unreachable")

    def _reflect(self, instruction, memory, trajectory, record) -> str:
        base = self._review_messages(REFLECTION_SYSTEM, instruction, memory, trajectory, record, "reflect")
        messages = base
        for attempt in range(self.config.max_parse_attempts):
            reply = self._complete(messages, "reflect", record)
            try:
                if reply.finish_reason == "length":
                    raise ProtocolError("Reflection was truncated; make it shorter")
                reflection = response_text(reply.content)
                if not reflection or len(reflection) > self.config.max_reflection_chars:
                    raise ProtocolError(f"Reflection must contain 1..{self.config.max_reflection_chars} characters")
                # A role/protocol mix-up must not become episodic memory.
                try:
                    accidental_action = json.loads(reflection)
                except ValueError:
                    accidental_action = None
                if isinstance(accidental_action, dict) and ("commands" in accidental_action or "task_complete" in accidental_action):
                    raise ProtocolError("Reflection must be verbal lessons and a plan, not an action object")
                return reflection
            except ProtocolError as exc:
                self._log("invalid_reflection", trial=record.index, attempt=attempt + 1, error=str(exc))
                if attempt + 1 == self.config.max_parse_attempts:
                    raise
                messages = [*base, {"role": "user", "content": f"Invalid reflection: {exc}. Regenerate concise reflective text."}]
        raise AssertionError("unreachable")

    def _rollout(self, instruction: str, memory: list[str], terminal: Terminal,
                 record: TrialResult) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": ACTOR_SYSTEM},
                    {"role": "user", "content": trial_prompt(instruction, memory, record.index)}]
        if self._size(messages) >= self.config.max_context_chars - self.config.context_reserve_chars:
            raise _Stopped("max_context_chars_reached")
        self._phase = "terminal"
        self._time_budget()
        initial = terminal.observe()
        self._log("initial_observation", trial=record.index, observation=initial)
        self._time_budget()
        messages.append({"role": "user", "content": "Current terminal observation:\n" + clip_text(initial, self.config.max_observation_chars)})
        previous_pair = None
        repeats = 0
        for _ in range(self.config.max_steps_per_trial):
            self._retry_budget()
            if self._size(messages) >= self.config.max_context_chars - self.config.context_reserve_chars:
                record.stop_reason = "trial_context_limit"
                break
            self._phase = "actor"
            action = self._action(messages, record)
            record.actor_steps += 1
            if action.task_complete:
                record.final_answer = action.final_answer
                record.stop_reason = "actor_complete"
                break
            loop_detected = False
            for command in action.commands:
                self._time_budget()
                if self._result.tool_calls >= self.config.max_tool_calls:
                    raise _Stopped("max_tool_calls_reached")
                self._phase = "terminal"
                self._result.tool_calls += 1
                record.tool_calls += 1
                duration = min(command.duration, max(0.0, self._deadline - time.monotonic()))
                self._log("terminal_input", trial=record.index, command_id=record.tool_calls,
                          keystrokes=command.keystrokes, duration=duration)
                observed = terminal.execute(command.keystrokes, duration)
                self._log("terminal_output", trial=record.index, command_id=record.tool_calls,
                          observation=observed)
                self._time_budget()
                remaining = max(200, self.config.max_context_chars - self._size(messages) - 1000)
                messages.append({"role": "user", "content": f"Observation for executed command {record.tool_calls}:\n" +
                                 clip_text(observed, min(self.config.max_observation_chars, remaining))})
                # Waiting is not a repeated failed action: long builds legitimately poll.
                pair = (command.keystrokes, observed)
                repeats = repeats + 1 if command.keystrokes.strip() and pair == previous_pair else 1
                previous_pair = pair if command.keystrokes.strip() else None
                if command.keystrokes.strip() and repeats >= self.config.repeat_action_limit:
                    record.stop_reason = "repeated_action_observation"
                    loop_detected = True
                    break
                if self._size(messages) >= self.config.max_context_chars - self.config.context_reserve_chars:
                    record.stop_reason = "trial_context_limit"
                    loop_detected = True
                    break
            if loop_detected:
                break
        else:
            record.stop_reason = "max_steps_per_trial_reached"
        return messages[1:]

    def run(self, instruction: str, terminal: Terminal) -> RunResult:
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("instruction must be a nonempty string")
        started = time.monotonic()
        self._deadline = started + self.config.max_total_seconds
        self._result = RunResult()
        self._phase = "initialization"
        memory: deque[str] = deque(maxlen=self.config.memory_size)
        self._log("run_start", config=asdict(self.config), instruction=instruction,
                  environment_policy=self._result.environment_policy)
        record = None
        trial_started = started
        try:
            for index in range(1, self.config.max_trials + 1):
                self._retry_budget()
                record = TrialResult(index=index, memory_before=list(memory))
                trial_started = time.monotonic()
                self._result.trials.append(record)
                self._log("trial_start", trial=index, memory=list(memory))
                trajectory = self._rollout(instruction, list(memory), terminal, record)
                self._result.final_answer = record.final_answer
                self._phase = "evaluation"
                record.evaluation = self._evaluate(instruction, list(memory), trajectory, record)
                self._log("evaluation", trial=index, evaluation=asdict(record.evaluation))
                if record.evaluation.passed:
                    self._result.stop_reason = "evaluator_passed"
                    break
                if index == self.config.max_trials:
                    self._result.stop_reason = "max_trials_reached"
                    break
                # No reflection when global budgets make another trial impossible.
                self._retry_budget()
                if self.config.max_model_calls - self._result.model_calls < 2:
                    raise _Stopped("insufficient_model_calls_for_retry")
                self._phase = "reflection"
                record.reflection = self._reflect(instruction, list(memory), trajectory, record)
                memory.append(record.reflection)
                self._result.memory = list(memory)
                self._log("reflection", trial=index, reflection=record.reflection, memory=list(memory))
                record.elapsed_seconds = time.monotonic() - trial_started
                self._log("trial_end", trial=index, record=asdict(record))
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
            if record is not None:
                record.elapsed_seconds = time.monotonic() - trial_started
                if not record.stop_reason:
                    record.stop_reason = self._result.stop_reason
                # Never substitute a previous trial's answer for an unfinished last trial.
                self._result.final_answer = record.final_answer
            self._result.memory = list(memory)
            self._result.elapsed_seconds = time.monotonic() - started
            self._log("run_end", result=asdict(self._result))
            if self.logger is not None:
                self.logger.save("result.json", self._result)
        return self._result
