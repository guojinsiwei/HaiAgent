"""Execution-kernel checks with scripted model replies and fake terminal output."""
from collections import deque
from copy import deepcopy
import json
import re

import pytest

from recuris.audit import JsonlLogger
from recuris.client import ModelClientError, ModelReply
from recuris.engine import RecurisConfig, RecurisRunner, parse_exit_receipt
from recuris.memory import load_memory


def initialization():
    return {"goals": [{"id": "artifact", "description": "Deliver checked artifact", "verification": {
        "command": "python public_check.py", "contains": ["PUBLIC_OK"]}}]}


def action(operation, keys="", goal_id="", answer=""):
    return {"analysis": "Use observed evidence", "operation": operation, "keystrokes": keys,
            "duration": 0, "goal_id": goal_id, "final_answer": answer}


def update(status="pending", rid=None):
    return {"updates": [{"goal_id": "artifact", "status": status,
                         "evidence_ids": [rid] if rid else [], "blocker": ""}],
            "new_goals": [], "revised_verifications": []}


class ScriptedClient:
    def __init__(self, *steps):
        self.steps = deque(steps)
        self.requests = []

    def complete(self, messages, *, purpose, deadline_monotonic=None):
        expected, response = self.steps.popleft()
        assert purpose == expected
        assert deadline_monotonic is not None
        self.requests.append((purpose, deepcopy(messages)))
        if isinstance(response, BaseException):
            raise response
        content = response if isinstance(response, str) else json.dumps(response)
        count = len(self.requests)
        return ModelReply(content, input_tokens=10 + count, output_tokens=count)


class FakeTerminal:
    def __init__(self, *, exit_code=0, split_receipt=False):
        self.calls = []
        self.exit_code = exit_code
        self.split_receipt = split_receipt
        self.pending = None

    def observe(self):
        return "shell ready"

    def execute(self, keys, duration):
        self.calls.append((keys, duration))
        match = re.search(r"__RECURIS_([0-9a-f]{32})__=", keys)
        if match:
            self.pending = "\n__RECURIS_" + match[1] + "__=" + str(self.exit_code) + "\n"
            start = "\n__RECURIS_BEGIN_" + match[1] + "__\n"
            if self.split_receipt:
                return start + "PUBLIC_OK\nverification in progress"
            result, self.pending = self.pending, None
            return start + "PUBLIC_OK" + result
        if keys == "" and self.pending:
            result, self.pending = self.pending, None
            return result
        return "ordinary terminal output"


def test_full_execution_separates_actor_and_state_updates_accounts_usage_and_records_evidence(tmp_path):
    keys = "cat > artifact.py <<'PY'\nprint('hello')\nPY\n"
    client = ScriptedClient(
        ("initialize", initialization()), ("act", action("execute", keys)), ("update", update()),
        ("act", action("verify", goal_id="artifact")), ("update", update("done", "receipt-2")),
        ("act", action("finish", answer="Public artifact check passed.")),
    )
    memory = load_memory()
    memory["E"] = [{"id": "inspect-first", "description": "Inspect artifact", "content": "Inspect before changing.", "tags": ["artifact"]}]
    memory["rho"]["trigger"] = "first_turn"
    terminal = FakeTerminal()
    result = RecurisRunner(client, memory=memory, logger=JsonlLogger(tmp_path)).run("Deliver artifact", terminal)
    assert result.stop_reason == "task_complete" and result.error is None
    assert result.official_success is None
    assert (result.model_calls, result.tool_calls, result.steps) == (6, 2, 3)
    assert (result.input_tokens, result.output_tokens) == (81, 21)
    assert terminal.calls[0] == (keys, 0)
    assert "python public_check.py" in terminal.calls[1][0]
    assert [p for p, _ in client.requests] == ["initialize", "act", "update", "act", "update", "act"]
    assert result.trace[0]["invoked_skills"] == ["inspect-first"]
    assert result.trace[1]["invoked_skills"] == []
    assert "Inspect before changing." in client.requests[3][1][1]["content"]
    assert result.trace[1]["checker_decisions"][0]["accepted"] is True
    assert result.working_state[0]["evidence_ids"] == ["receipt-2"]
    saved = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert saved["official_success"] is None and saved["tool_calls"] == 2
    assert not client.steps


def test_finish_cannot_bypass_checks_and_synthetic_rejection_cannot_prove_done():
    client = ScriptedClient(("initialize", initialization()), ("act", action("finish", answer="unsupported")),
                            ("update", update("done", "receipt-1")), ("act", action("stop", answer="Cannot verify.")))
    terminal = FakeTerminal()
    result = RecurisRunner(client).run("Deliver artifact", terminal)
    assert result.stop_reason == "actor_stopped_incomplete"
    assert result.final_answer == "Cannot verify."
    assert result.trace[0]["observation"]["kind"] == "rejected_completion"
    assert result.trace[0]["checker_decisions"][0]["accepted"] is False
    assert result.working_state[0]["status"] == "pending"
    assert terminal.calls == []


def test_verification_receipt_can_arrive_in_multiple_terminal_observations():
    client = ScriptedClient(("initialize", initialization()), ("act", action("verify", goal_id="artifact")),
                            ("update", update("done", "receipt-1")), ("act", action("finish")))
    terminal = FakeTerminal(split_receipt=True)
    result = RecurisRunner(client).run("Deliver artifact", terminal)
    assert result.stop_reason == "task_complete"
    assert result.tool_calls == 2 and terminal.calls[1][0] == ""
    assert result.trace[0]["observation"]["exit_code"] == 0


def test_failed_public_check_cannot_complete_even_when_model_requests_done():
    client = ScriptedClient(("initialize", initialization()), ("act", action("verify", goal_id="artifact")),
                            ("update", update("done", "receipt-1")), ("act", action("stop")))
    result = RecurisRunner(client).run("Deliver artifact", FakeTerminal(exit_code=1))
    assert result.stop_reason == "actor_stopped_incomplete"
    assert result.trace[0]["observation"]["exit_code"] == 1
    assert not result.trace[0]["checker_decisions"][0]["accepted"]


def test_new_terminal_input_invalidates_prior_completion_and_old_receipts():
    client = ScriptedClient(("initialize", initialization()), ("act", action("verify", goal_id="artifact")),
                            ("update", update("done", "receipt-1")), ("act", action("execute", "touch artifact.py\n")),
                            ("update", update("done", "receipt-1")), ("act", action("stop")))
    result = RecurisRunner(client).run("Deliver artifact", FakeTerminal())
    assert result.trace[0]["state_after"][0]["status"] == "done"
    assert result.trace[1]["state_after"][0]["status"] == "pending"
    assert not result.trace[1]["checker_decisions"][0]["accepted"]
    assert result.stop_reason == "actor_stopped_incomplete"


def test_protocol_retry_is_bounded_and_all_replies_are_billed():
    client = ScriptedClient(("initialize", "not JSON"), ("initialize", initialization()), ("act", action("stop")))
    result = RecurisRunner(client).run("Deliver artifact", FakeTerminal())
    assert result.stop_reason == "actor_stopped_incomplete" and result.model_calls == 3
    assert (result.input_tokens, result.output_tokens) == (36, 6)
    assert "Protocol error" in client.requests[1][1][-1]["content"]
    bad = ScriptedClient(("initialize", "invalid"), ("initialize", "still invalid"))
    failed = RecurisRunner(bad).run("Deliver artifact", FakeTerminal())
    assert failed.stop_reason == "protocol_error" and failed.model_calls == 2
    assert failed.working_state == [] and failed.tool_calls == 0


@pytest.mark.parametrize("setting,reason,remaining", [
    ({"max_model_calls": 1}, "max_model_calls_reached", 5),
    ({"max_steps": 1}, "max_steps_reached", 3),
    ({"max_tool_calls": 1}, "max_tool_calls_reached", 2),
])
def test_execution_budgets_stop_before_extra_work(setting, reason, remaining):
    client = ScriptedClient(("initialize", initialization()), ("act", action("execute", "pwd\n")),
                            ("update", update()), ("act", action("execute", "ls\n")),
                            ("update", update()), ("act", action("stop")))
    terminal = FakeTerminal()
    result = RecurisRunner(client, RecurisConfig(**setting)).run("Deliver artifact", terminal)
    assert result.stop_reason == reason and result.error is None
    assert len(client.steps) == remaining
    assert len(terminal.calls) <= 1


def test_model_error_usage_is_not_lost_and_deadline_caps_future_work(monkeypatch):
    error = ModelClientError("provider unavailable", input_tokens=17, output_tokens=5)
    result = RecurisRunner(ScriptedClient(("initialize", error))).run("Deliver artifact", FakeTerminal())
    assert result.stop_reason == "model_error"
    assert (result.input_tokens, result.output_tokens) == (17, 5)
    clock = [0.0]
    monkeypatch.setattr("recuris.engine.time.monotonic", lambda: clock[0])
    class LateClient(ScriptedClient):
        def complete(self, *args, **kwargs):
            reply = super().complete(*args, **kwargs)
            clock[0] = 2.0
            return reply
    result = RecurisRunner(LateClient(("initialize", initialization())), RecurisConfig(max_total_seconds=1)).run("Deliver artifact", FakeTerminal())
    assert result.stop_reason == "max_total_seconds_reached"
    assert result.model_calls == 1 and result.tool_calls == 0
    assert (result.input_tokens, result.output_tokens) == (11, 1)


def test_reusing_runner_resets_task_state_and_does_not_mutate_memory():
    memory = load_memory()
    original = deepcopy(memory)
    client = ScriptedClient(("initialize", initialization()), ("act", action("stop")),
                            ("initialize", initialization()), ("act", action("stop")))
    runner = RecurisRunner(client, memory=memory)
    first = runner.run("First artifact", FakeTerminal())
    first.working_state[0]["status"] = "done"
    second = runner.run("Second artifact", FakeTerminal())
    assert second.working_state[0]["status"] == "pending"
    assert first.model_calls == second.model_calls == 2
    assert len(second.trace) == 1
    assert memory == original == runner.memory


def test_receipt_parser_rejects_echoed_commands_duplicate_markers_and_wrong_nonce():
    nonce = "a" * 32
    start = "__RECURIS_BEGIN_" + nonce + "__\n"
    marker = "__RECURIS_" + nonce + "__=0"
    assert parse_exit_receipt(start + "PUBLIC_OK\n" + marker + "\r\n", nonce) == 0
    for text in ("printf '" + marker + "'", start + marker + "\n" + marker, start + "__RECURIS_wrong__=0\n", start + marker[:-1] + "256\n", "PUBLIC_OK\n" + marker):
        assert parse_exit_receipt(text, nonce) is None


def test_command_echo_outside_verifier_markers_is_not_output_evidence():
    class EchoOnlyTerminal(FakeTerminal):
        def execute(self, keys, duration):
            self.calls.append((keys, duration))
            nonce = re.search(r"__RECURIS_([0-9a-f]{32})__=", keys)[1]
            return ("echo PUBLIC_OK; " + keys + "\n__RECURIS_BEGIN_" + nonce
                    + "__\nno supporting text\n__RECURIS_" + nonce + "__=0\n")
    client = ScriptedClient(("initialize", initialization()), ("act", action("verify", goal_id="artifact")),
                            ("update", update("done", "receipt-1")), ("act", action("stop")))
    result = RecurisRunner(client).run("Deliver artifact", EchoOnlyTerminal())
    assert result.trace[0]["observation"]["exit_code"] == 0
    assert "PUBLIC_OK" not in result.trace[0]["observation"]["output"]
    assert result.working_state[0]["status"] == "pending"
