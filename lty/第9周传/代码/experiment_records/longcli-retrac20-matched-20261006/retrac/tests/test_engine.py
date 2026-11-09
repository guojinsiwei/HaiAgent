import json

import pytest

from retrac.client import ModelReply
from retrac.engine import ProtocolError, RetracConfig, RetracRunner, parse_action, validate_state


def state(tag="memory", variant="full"):
    headings = ["Current Answer", "Facts & Evidence Collected", "Analysis & Conclusions",
                "Source Inventory & Verification Status", "Uncertainties, Limitations, Gaps",
                "Failed attempts", "Uncompleted proposals", "Discarded possibilities"]
    return "\n".join(f"{i}) {title}\n{tag}: evidence r1:tool1" for i, title in enumerate(headings[:5] if variant == "base" else headings))


def action(answer="", commands=None, done=True):
    return json.dumps({"analysis": "Check observed evidence", "commands": commands or [],
                       "task_complete": done, "final_answer": answer})


class ScriptedClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def complete(self, messages, *, purpose, deadline_monotonic=None):
        self.calls.append((purpose, [dict(m) for m in messages]))
        text = next(self.responses)
        if isinstance(text, Exception):
            raise text
        return ModelReply(text, input_tokens=10, output_tokens=4, finish_reason="stop")


class FakeTerminal:
    def __init__(self, output="visible state"):
        self.commands = []
        self.output = output
        self.observations = 0

    def observe(self):
        self.observations += 1
        return self.output

    def execute(self, keystrokes, duration):
        self.commands.append((keystrokes, duration))
        return "RESULT_ONLY_IN_ROUND_ONE"


def test_recursive_state_fresh_context_last_answer_and_total_accounting():
    client = ScriptedClient([
        action(commands=[{"keystrokes": "echo probe\n", "duration": 0.1}], done=False), action("first candidate"),
        state("S1"), action("second candidate"), state("S2"), action("last candidate"),
    ])
    terminal = FakeTerminal()
    result = RetracRunner(client, RetracConfig(rounds=3)).run("original task", terminal)
    assert result.stop_reason == "rounds_completed"
    assert result.final_answer == "last candidate"
    assert result.official_success is None
    assert (result.model_calls, result.tool_calls, result.input_tokens, result.output_tokens) == (6, 1, 60, 24)
    assert terminal.observations == 3
    assert len(terminal.commands) == 1
    assert [purpose for purpose, _ in client.calls] == ["act", "act", "compress", "act", "compress", "act"]
    second_input = client.calls[3][1]
    assert second_input[0]["role"] == "system" and second_input[1]["role"] == "user"
    assert "S1" in second_input[1]["content"] and "original task" in second_input[1]["content"]
    assert "RESULT_ONLY_IN_ROUND_ONE" not in json.dumps(second_input)
    assert "S1" in json.dumps(client.calls[4][1])  # recursive compressor includes S_prev
    third_input = json.dumps(client.calls[5][1])
    assert "S2" in third_input and "S1" not in third_input


def test_does_not_early_stop_on_self_reported_completion():
    client = ScriptedClient([action("done"), state(), action("rechecked")])
    result = RetracRunner(client, RetracConfig(rounds=2)).run("task", FakeTerminal())
    assert len(result.rounds) == 2
    assert result.final_answer == "rechecked"


def test_step_limit_still_compresses_and_continues():
    client = ScriptedClient([action(commands=[{"keystrokes": "ls\n"}], done=False), state(), action("done")])
    result = RetracRunner(client, RetracConfig(rounds=2, max_steps_per_round=1)).run("task", FakeTerminal())
    assert result.rounds[0].stop_reason == "step_limit"
    assert result.final_answer == "done"


def test_tool_budget_is_global_across_rounds_and_inside_batches():
    client = ScriptedClient([action(commands=[{"keystrokes": "a\n"}, {"keystrokes": "b\n"}], done=False)])
    terminal = FakeTerminal()
    result = RetracRunner(client, RetracConfig(rounds=3, max_tool_calls=1)).run("task", terminal)
    assert result.stop_reason == "max_tool_calls_reached"
    assert [cmd for cmd, _ in terminal.commands] == ["a\n"]


def test_last_model_call_can_execute_but_cannot_start_another_round():
    client = ScriptedClient([action(commands=[{"keystrokes": "a\n"}], done=False)])
    terminal = FakeTerminal()
    result = RetracRunner(client, RetracConfig(rounds=2, max_model_calls=1)).run("task", terminal)
    assert result.stop_reason == "max_model_calls_reached"
    assert result.tool_calls == 1


def test_bad_json_retries_without_executing_commands():
    client = ScriptedClient(["not json", action("ok")])
    terminal = FakeTerminal()
    result = RetracRunner(client, RetracConfig(rounds=1)).run("task", terminal)
    assert result.final_answer == "ok" and result.model_calls == 2
    assert terminal.commands == []
    assert "No commands were executed" in client.calls[1][1][-1]["content"]


def test_invalid_compression_is_not_replaced_by_silent_fallback():
    client = ScriptedClient([action("first"), "unstructured", "still invalid"])
    result = RetracRunner(client, RetracConfig(rounds=2)).run("task", FakeTerminal())
    assert result.stop_reason == "compression_error"
    assert len(result.rounds) == 1
    assert result.input_tokens == 30


def test_terminal_error_does_not_turn_into_success():
    class Broken(FakeTerminal):
        def execute(self, *args):
            raise RuntimeError("terminal disappeared")
    result = RetracRunner(ScriptedClient([action(commands=[{"keystrokes": "x\n"}], done=False)]), RetracConfig(rounds=1)).run("task", Broken())
    assert result.stop_reason == "terminal_error"
    assert result.official_success is None
    assert result.final_answer == ""


def test_observation_limit_keeps_head_tail_and_marks_omission():
    terminal = FakeTerminal("HEAD" + "x" * 5000 + "TAIL")
    client = ScriptedClient([action("done")])
    RetracRunner(client, RetracConfig(rounds=1, max_observation_chars=200)).run("task", terminal)
    text = client.calls[0][1][-1]["content"]
    assert "HEAD" in text and "TAIL" in text and "truncated" in text
    assert len(text) < 250


def test_oversized_initial_task_fails_explicitly_without_truncating_task():
    client = ScriptedClient([])
    result = RetracRunner(client, RetracConfig(max_context_chars=2000, compression_reserve_chars=500)).run("x" * 3000, FakeTerminal())
    assert result.stop_reason == "initial_context_too_large"
    assert client.calls == []


@pytest.mark.parametrize("bad", [True, -1, float("nan"), float("inf"), 121])
def test_invalid_command_durations_rejected(bad):
    with pytest.raises(ProtocolError):
        parse_action(action(commands=[{"keystrokes": "x\n", "duration": bad}]))


def test_whole_batch_is_validated_before_any_command_executes():
    invalid = action(commands=[{"keystrokes": "valid\n"}, {"keystrokes": "invalid", "duration": -2}])
    terminal = FakeTerminal()
    result = RetracRunner(ScriptedClient([invalid, invalid]), RetracConfig(rounds=1)).run("task", terminal)
    assert result.stop_reason == "protocol_error" and terminal.commands == []


def test_base_full_state_requirements_and_no_empty_facets():
    assert validate_state(state(variant="base"), "base", 10000)
    with pytest.raises(ProtocolError):
        validate_state(state(variant="base"), "full", 10000)
    with pytest.raises(ProtocolError):
        validate_state("0) Current Answer\n1) Facts & Evidence Collected\nNone", "base", 10000)


@pytest.mark.parametrize("config", [{"rounds": True}, {"rounds": 0}, {"summary_variant": "other"},
                                   {"max_command_duration": float("nan")}, {"max_parse_attempts": 0}])
def test_config_validation(config):
    with pytest.raises(ValueError):
        RetracConfig(**config)


def test_large_tool_output_fits_compression_and_rolls_over():
    class VerboseTerminal(FakeTerminal):
        def execute(self, keystrokes, duration):
            self.commands.append((keystrokes, duration))
            return "HEAD" + "x" * 50000 + "TAIL"
    client = ScriptedClient([action(commands=[{"keystrokes": "cat log\n"}], done=False), state(), action("done")])
    result = RetracRunner(client, RetracConfig(rounds=2, max_context_chars=24000,
                                              compression_reserve_chars=6000)).run("task", VerboseTerminal())
    assert result.stop_reason == "rounds_completed"
    assert result.rounds[0].stop_reason == "context_limit"
    compression = client.calls[1][1]
    assert RetracRunner._size(compression) <= 24000
    assert "truncated" in json.dumps(compression)


def test_completion_cannot_hide_unobserved_commands():
    with pytest.raises(ProtocolError, match="Inspect command"):
        parse_action(action("success", [{"keystrokes": "write something\n"}]))


def test_model_error_usage_is_accounted():
    from retrac.client import ModelClientError
    error = ModelClientError("empty response", input_tokens=21, output_tokens=9)
    result = RetracRunner(ScriptedClient([error]), RetracConfig(rounds=1)).run("task", FakeTerminal())
    assert result.stop_reason == "model_error"
    assert (result.input_tokens, result.output_tokens) == (21, 9)


def test_late_response_usage_and_stop_reason():
    from retrac.client import ModelDeadlineExceeded
    error = ModelDeadlineExceeded("late response", input_tokens=11, output_tokens=5)
    result = RetracRunner(ScriptedClient([error]), RetracConfig(rounds=1)).run("task", FakeTerminal())
    assert result.stop_reason == "max_total_seconds_reached"
    assert (result.input_tokens, result.output_tokens) == (11, 5)


def test_incomplete_last_round_does_not_return_an_earlier_answer():
    client = ScriptedClient([action("old answer"), state(), RuntimeError("offline")])
    result = RetracRunner(client, RetracConfig(rounds=2)).run("task", FakeTerminal())
    assert result.final_answer == ""
    assert result.rounds[0].final_answer == "old answer"
