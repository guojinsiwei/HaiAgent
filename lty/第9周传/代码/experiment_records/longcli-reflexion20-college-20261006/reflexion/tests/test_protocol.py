import json

import pytest

from reflexion.protocol import ProtocolError, parse_action, parse_evaluation


def action(**changes):
    value = {"analysis": "check", "commands": [], "task_complete": True, "final_answer": "done"}
    value.update(changes)
    return json.dumps(value)


@pytest.mark.parametrize("value", [
    '{}', '[]', '{"passed":true,"passed":false}',
    action(task_complete="true"), action(commands=[{"keystrokes": "pwd\n", "duration": 1}]),
    action(task_complete=False), action(analysis=None),
    action(task_complete=False, commands=[{"keystrokes": "ls\n", "duration": True}]),
    action(task_complete=False, commands=[{"keystrokes": "ls\n", "duration": float("nan")}]),
    action(task_complete=False, commands=[{"keystrokes": "ls\n", "duration": -1}]),
    action(task_complete=False, commands=[{"keystrokes": "ls\n", "duration": 121}]),
    action(task_complete=False, commands=[{"keystrokes": "ls\n", "duration": 10**400}]),
    action(task_complete=False, commands=[{"keystrokes": "ls\n"}]),
    action(task_complete=False, commands=[{"keystrokes": "bad\x00", "duration": 1}]),
])
def test_reject_action_before_execution(value):
    with pytest.raises(ProtocolError):
        parse_action(value)


def test_late_invalid_batch_member_rejects_entire_action():
    with pytest.raises(ProtocolError):
        parse_action(action(task_complete=False, commands=[
            {"keystrokes": "touch something\n", "duration": 1},
            {"keystrokes": "bad\n", "duration": "invalid"},
        ]))


def test_exact_heredoc_control_and_polling_payloads():
    keys = ["cat > x <<'EOF'\na\nb\nEOF\n", "C-c", ""]
    parsed = parse_action(action(task_complete=False, commands=[
        {"keystrokes": text, "duration": 0} for text in keys
    ]))
    assert [command.keystrokes for command in parsed.commands] == keys


@pytest.mark.parametrize("value", [
    {"passed": "true", "feedback": "ok", "evidence": ["test passed"]},
    {"passed": True, "feedback": "ok", "evidence": []},
    {"passed": True, "feedback": "", "evidence": ["test passed"]},
    {"passed": True, "feedback": "ok", "evidence": [""]},
    {"passed": True, "feedback": "ok", "evidence": "actor says done"},
    {"passed": False, "feedback": "failed", "evidence": [], "official_success": True},
])
def test_evaluation_rejects_unsupported_verdict_schema(value):
    with pytest.raises(ProtocolError):
        parse_evaluation(json.dumps(value))


def test_failure_can_have_no_evidence_but_pass_requires_evidence():
    assert not parse_evaluation('{"passed":false,"feedback":"No tests observed","evidence":[]}').passed
    assert parse_evaluation('{"passed":true,"feedback":"Requirement checked","evidence":["check output"]}').passed

