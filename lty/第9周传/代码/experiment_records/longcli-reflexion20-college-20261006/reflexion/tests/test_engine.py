"""Offline state-machine checks: scripted model text and in-memory terminal only."""

from collections import deque
from copy import deepcopy
import json

import pytest

from reflexion.client import ModelClientError, ModelDeadlineExceeded, ModelReply
from reflexion.engine import ReflexionConfig, ReflexionRunner
from reflexion.protocol import ProtocolError, parse_action


def act(command=None, *, answer="", duration=0):
    return json.dumps({
        "analysis": "Inspect the observed result",
        "commands": [] if command is None else [{"keystrokes": command, "duration": duration}],
        "task_complete": command is None,
        "final_answer": answer,
    })


def verdict(passed, *, evidence=None):
    return json.dumps({
        "passed": passed,
        "feedback": "The required artifact was observed" if passed else "The artifact is still missing",
        "evidence": (["terminal showed artifact.txt"] if evidence is None else evidence),
    })


class ScriptedClient:
    def __init__(self, *steps):
        self.steps = deque(steps)
        self.requests = []

    def complete(self, messages, *, purpose, deadline_monotonic=None):
        self.requests.append({"purpose": purpose, "messages": deepcopy(messages), "deadline": deadline_monotonic})
        if not self.steps:
            raise AssertionError(f"Unexpected model call: {purpose}")
        expected_purpose, result = self.steps.popleft()
        assert purpose == expected_purpose
        if callable(result):
            result = result()
        if isinstance(result, Exception):
            raise result
        return result if isinstance(result, ModelReply) else ModelReply(result, input_tokens=3, output_tokens=2)


class MemoryTerminal:
    def __init__(self, *outputs, initial="artifact.txt is absent"):
        self.outputs = deque(outputs)
        self.current = initial
        self.observations = []
        self.commands = []

    def observe(self):
        self.observations.append(self.current)
        return self.current

    def execute(self, keystrokes, duration):
        self.commands.append((keystrokes, duration))
        result = self.outputs.popleft() if self.outputs else self.current
        if callable(result):
            result = result()
        if isinstance(result, Exception):
            raise result
        self.current = result
        return result


class MemoryLogger:
    def __init__(self):
        self.events = []
        self.snapshots = {}

    def write(self, event, **payload):
        self.events.append((event, deepcopy(payload)))

    def save(self, name, value):
        self.snapshots[name] = deepcopy(value)


def contents(request):
    return "\n".join(item["content"] for item in request["messages"])


def test_failed_trial_reflects_with_feedback_and_restarts_actor_on_persistent_terminal():
    lesson = "I used the wrong path; inspect /work/output before writing again."
    client = ScriptedClient(
        ("act", act("inspect-path\n")),
        ("reflect", lesson),
        ("act", act(answer="Observed the repaired artifact")),
        ("evaluate", verdict(True)),
    )
    terminal = MemoryTerminal("UNIQUE_FAILED_TRIAL_OUTPUT: /work/output exists")
    result = ReflexionRunner(client, ReflexionConfig(max_steps_per_trial=1)).run("Create /work/output", terminal)

    assert result.stop_reason == "evaluator_passed"
    assert result.official_success is None
    assert result.environment_policy == "persistent_terminal_and_filesystem"
    assert len(result.trials) == 2
    first, second = result.trials
    assert first.evaluation.source == "failure_heuristic"
    assert first.stop_reason == "max_steps_per_trial_reached"
    assert first.reflection == lesson
    assert second.memory_before == [lesson]
    reflection_input = contents(client.requests[1])
    assert "max_steps_per_trial_reached" in reflection_input
    assert "UNIQUE_FAILED_TRIAL_OUTPUT" in reflection_input
    assert "Create /work/output" in reflection_input
    next_actor = client.requests[2]["messages"]
    assert [message["role"] for message in next_actor] == ["system", "user", "user"]
    assert lesson in next_actor[1]["content"]
    assert "inspect-path" not in contents(client.requests[2])
    assert "UNIQUE_FAILED_TRIAL_OUTPUT" in next_actor[2]["content"]
    assert terminal.observations == ["artifact.txt is absent", "UNIQUE_FAILED_TRIAL_OUTPUT: /work/output exists"]
    assert result.model_calls == 4 and result.tool_calls == 1
    assert (result.input_tokens, result.output_tokens) == (12, 8)
    assert sum(trial.model_calls for trial in result.trials) == result.model_calls


def test_reflections_are_fifo_and_last_failed_trial_does_not_reflect():
    steps = []
    for index in range(1, 5):
        steps.extend([("act", act(answer=f"unverified answer {index}")), ("evaluate", verdict(False))])
        if index < 4:
            steps.append(("reflect", f"lesson {index}"))
    client = ScriptedClient(*steps)
    result = ReflexionRunner(client, ReflexionConfig(max_trials=4, memory_size=2)).run("Make artifact", MemoryTerminal())

    assert result.stop_reason == "max_trials_reached"
    assert [trial.memory_before for trial in result.trials] == [[], ["lesson 1"], ["lesson 1", "lesson 2"], ["lesson 2", "lesson 3"]]
    assert result.memory == ["lesson 2", "lesson 3"]
    assert result.trials[-1].reflection is None
    assert not client.steps


def test_same_runner_does_not_share_memory_or_accounting_between_tasks():
    client = ScriptedClient(
        ("act", act(answer="first task attempt")), ("evaluate", verdict(False)),
        ("reflect", "FIRST_TASK_PRIVATE_LESSON"),
        ("act", act(answer="first task done")), ("evaluate", verdict(True)),
        ("act", act(answer="second task done")), ("evaluate", verdict(True)),
    )
    runner = ReflexionRunner(client)
    first = runner.run("FIRST_TASK_PRIVATE_INSTRUCTION", MemoryTerminal())
    second = runner.run("Second independent task", MemoryTerminal(initial="artifact.txt"))

    assert first.memory == ["FIRST_TASK_PRIVATE_LESSON"]
    assert second.memory == [] and second.trials[0].memory_before == []
    assert second.model_calls == 2 and second.input_tokens == 6
    assert len(first.trials) == 2
    assert "FIRST_TASK_PRIVATE" not in contents(client.requests[-2])


def test_actor_completion_requires_separate_evaluation_and_evidence_for_pass():
    client = ScriptedClient(
        ("act", act(answer="I claim success")),
        ("evaluate", verdict(True, evidence=[])),
        ("evaluate", verdict(False, evidence=[])),
    )
    result = ReflexionRunner(client, ReflexionConfig(max_trials=1)).run("Make artifact", MemoryTerminal())

    assert result.stop_reason == "max_trials_reached"
    assert result.trials[0].evaluation.passed is False
    assert result.official_success is None
    assert "observed supporting evidence" in contents(client.requests[2])
    assert result.model_calls == 3


def test_protocol_repair_validates_entire_command_batch_before_any_execution():
    malformed = json.loads(act("must-not-execute\n"))
    malformed["commands"].append({"keystrokes": "invalid-duration\n", "duration": -1})
    client = ScriptedClient(
        ("act", json.dumps(malformed)),
        ("act", act("valid-command\n")),
        ("act", act(answer="checked")),
        ("evaluate", verdict(True)),
    )
    terminal = MemoryTerminal("artifact.txt")
    result = ReflexionRunner(client).run("Make artifact", terminal)

    assert result.stop_reason == "evaluator_passed"
    assert terminal.commands == [("valid-command\n", 0.0)]
    assert "No commands were executed" in contents(client.requests[1])
    assert "must-not-execute" not in contents(client.requests[1])


def test_truncated_action_never_executes_even_if_json_was_complete():
    client = ScriptedClient(
        ("act", ModelReply(act("untrusted-partial\n"), 5, 7, "length")),
        ("act", act(answer="observed completion")),
        ("evaluate", verdict(True)),
    )
    terminal = MemoryTerminal(initial="artifact.txt")
    result = ReflexionRunner(client).run("Make artifact", terminal)

    assert result.stop_reason == "evaluator_passed"
    assert terminal.commands == []
    assert (result.input_tokens, result.output_tokens) == (11, 11)


def test_reflection_rejects_action_json_and_removes_leading_reasoning_wrapper():
    client = ScriptedClient(
        ("act", act(answer="attempt")), ("evaluate", verdict(False)),
        ("reflect", act("wrong-role-command\n")),
        ("reflect", "<think>PRIVATE_DRAFT</think>\nI will inspect the observed path before retrying."),
        ("act", act(answer="done")), ("evaluate", verdict(True)),
    )
    terminal = MemoryTerminal()
    result = ReflexionRunner(client).run("Make artifact", terminal)

    assert result.stop_reason == "evaluator_passed"
    assert result.memory == ["I will inspect the observed path before retrying."]
    assert terminal.commands == []
    assert "wrong-role-command" not in contents(client.requests[-2])
    assert "PRIVATE_DRAFT" not in contents(client.requests[-2])


def test_repeated_failed_actions_trigger_heuristic_reflection_but_polls_do_not():
    client = ScriptedClient(
        ("act", act("same-failed-command\n")), ("act", act("same-failed-command\n")),
        ("reflect", "I should inspect the error and choose another command."),
        ("act", act(answer="done")), ("evaluate", verdict(True)),
    )
    terminal = MemoryTerminal("same error", "same error")
    result = ReflexionRunner(client, ReflexionConfig(repeat_action_limit=2)).run("Make artifact", terminal)
    assert result.trials[0].stop_reason == "repeated_action_observation"
    assert result.trials[0].evaluation.source == "failure_heuristic"
    assert terminal.commands == [("same-failed-command\n", 0.0)] * 2

    poll_client = ScriptedClient(
        ("act", act("")), ("act", act("")), ("act", act("")),
        ("act", act(answer="long job completed")), ("evaluate", verdict(True)),
    )
    poll_terminal = MemoryTerminal(initial="job running")
    poll_result = ReflexionRunner(poll_client, ReflexionConfig(repeat_action_limit=2)).run("Wait for artifact", poll_terminal)
    assert poll_result.stop_reason == "evaluator_passed"
    assert len(poll_result.trials) == 1
    assert len(poll_terminal.commands) == 3


def test_total_tool_budget_can_stop_a_multi_command_batch_without_executing_tail():
    batch = json.loads(act("allowed\n"))
    batch["commands"].append({"keystrokes": "budget-forbidden\n", "duration": 0})
    client = ScriptedClient(("act", json.dumps(batch)))
    terminal = MemoryTerminal("first executed")
    result = ReflexionRunner(client, ReflexionConfig(max_tool_calls=1)).run("Make artifact", terminal)

    assert result.stop_reason == "max_tool_calls_reached"
    assert terminal.commands == [("allowed\n", 0.0)]
    assert result.tool_calls == 1 and result.model_calls == 1
    assert result.trials[0].evaluation is None


def test_model_budget_prevents_reflection_when_retry_cannot_fit():
    client = ScriptedClient(("act", act(answer="attempt")), ("evaluate", verdict(False)))
    result = ReflexionRunner(client, ReflexionConfig(max_model_calls=3)).run("Make artifact", MemoryTerminal())

    assert result.stop_reason == "insufficient_model_calls_for_retry"
    assert result.memory == []
    assert result.model_calls == 2
    assert result.trials[0].reflection is None


def test_model_deadline_reply_is_counted_but_cannot_execute_commands(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr("reflexion.engine.time.monotonic", lambda: clock[0])

    def late_reply():
        clock[0] = 12.0
        return ModelReply(act("too-late\n"), 11, 13)

    client = ScriptedClient(("act", late_reply))
    terminal = MemoryTerminal()
    result = ReflexionRunner(client, ReflexionConfig(max_total_seconds=1)).run("Make artifact", terminal)

    assert result.stop_reason == "max_total_seconds_reached"
    assert (result.input_tokens, result.output_tokens) == (11, 13)
    assert terminal.commands == []
    assert client.requests[0]["deadline"] == 11.0


def test_deadline_exception_preserves_usage_and_stops_without_retry():
    client = ScriptedClient(("act", ModelDeadlineExceeded("deadline", input_tokens=17, output_tokens=19)))
    terminal = MemoryTerminal()
    result = ReflexionRunner(client).run("Make artifact", terminal)

    assert result.stop_reason == "max_total_seconds_reached"
    assert (result.input_tokens, result.output_tokens) == (17, 19)
    assert result.model_calls == 1 and terminal.commands == []


def test_command_wait_duration_is_capped_to_remaining_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("reflexion.engine.time.monotonic", lambda: clock[0])

    def delayed_action():
        clock[0] = 0.8
        return act("long-job\n", duration=120)

    client = ScriptedClient(
        ("act", delayed_action), ("act", act(answer="done")), ("evaluate", verdict(True)),
    )
    terminal = MemoryTerminal("artifact.txt")
    result = ReflexionRunner(client, ReflexionConfig(max_total_seconds=1)).run("Make artifact", terminal)

    assert result.stop_reason == "evaluator_passed"
    assert terminal.commands[0][1] == pytest.approx(0.2)
    assert all(request["deadline"] == 1.0 for request in client.requests)


def test_terminal_overrun_stops_before_further_model_call(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("reflexion.engine.time.monotonic", lambda: clock[0])

    def overrun():
        clock[0] = 2.0
        return "operation eventually returned"

    terminal = MemoryTerminal(overrun)
    client = ScriptedClient(("act", act("slow-job\n")))
    result = ReflexionRunner(client, ReflexionConfig(max_total_seconds=1)).run("Make artifact", terminal)

    assert result.stop_reason == "max_total_seconds_reached"
    assert result.model_calls == 1 and result.tool_calls == 1


def test_last_unfinished_trial_does_not_reuse_earlier_rejected_answer():
    client = ScriptedClient(
        ("act", act(answer="REJECTED_FIRST_ANSWER")), ("evaluate", verdict(False)),
        ("reflect", "I should finish the missing artifact."),
        ("act", ModelClientError("provider unavailable", input_tokens=23, output_tokens=29)),
    )
    result = ReflexionRunner(client).run("Make artifact", MemoryTerminal())

    assert result.stop_reason == "model_error" and result.error_phase == "actor"
    assert result.final_answer == ""
    assert result.trials[0].final_answer == "REJECTED_FIRST_ANSWER"
    assert result.trials[1].input_tokens == 23 and result.trials[1].output_tokens == 29
    assert (result.input_tokens, result.output_tokens) == (32, 35)


def test_terminal_failure_is_counted_and_identifies_error_phase():
    client = ScriptedClient(("act", act("unavailable-terminal\n")))
    result = ReflexionRunner(client).run("Make artifact", MemoryTerminal(RuntimeError("terminal disconnected")))

    assert result.stop_reason == "terminal_error" and result.error_phase == "terminal"
    assert result.tool_calls == 1 and result.trials[0].tool_calls == 1
    assert "terminal disconnected" in result.error


def test_context_limit_preserves_task_and_marks_clipped_review_evidence():
    client = ScriptedClient(("reflect", "I need shorter targeted observations."))
    logger = MemoryLogger()
    config = ReflexionConfig(
        max_trials=2, memory_size=1, max_reflection_chars=1000,
        max_context_chars=12000, context_reserve_chars=4000, max_observation_chars=9000,
    )
    result = ReflexionRunner(client, config, logger).run("EXACT_PUBLIC_REQUIREMENT", MemoryTerminal(initial="X" * 9000))

    assert result.stop_reason == "max_trials_reached"
    assert all(trial.stop_reason == "trial_context_limit" for trial in result.trials)
    assert all(trial.actor_steps == 0 for trial in result.trials)
    reflection_input = contents(client.requests[0])
    assert "EXACT_PUBLIC_REQUIREMENT" in reflection_input and "[TRUNCATED:" in reflection_input
    assert any(name == "review_evidence_truncated" for name, _ in logger.events)
    assert logger.snapshots["result.json"].stop_reason == "max_trials_reached"


def test_oversized_task_is_not_silently_truncated_or_sent_to_model():
    client, terminal = ScriptedClient(), MemoryTerminal()
    result = ReflexionRunner(client).run("T" * 130000, terminal)

    assert result.stop_reason == "max_context_chars_reached"
    assert client.requests == [] and terminal.observations == []


@pytest.mark.parametrize("payload", [
    '{"analysis":"x","commands":[],"task_complete":false,"task_complete":true,"final_answer":"x"}',
    json.dumps({"analysis": "x", "commands": [], "task_complete": "true", "final_answer": "x"}),
    json.dumps({"analysis": "x", "commands": [{"keystrokes": "x\n", "duration": 0}], "task_complete": True, "final_answer": "x"}),
    json.dumps({"analysis": "x", "commands": [{"keystrokes": "x\n", "duration": float("nan")}], "task_complete": False, "final_answer": ""}),
])
def test_unsafe_or_ambiguous_terminal_protocol_is_rejected(payload):
    with pytest.raises(ProtocolError):
        parse_action(payload)


def test_oversized_integer_duration_uses_protocol_error_instead_of_crashing():
    with pytest.raises(ProtocolError):
        parse_action(act("invalid-duration\n", duration=10 ** 400))
