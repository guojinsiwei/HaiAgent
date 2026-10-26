"""Offline tests of the non-evolvable observation-grounded commit kernel."""
from copy import deepcopy

import pytest

from recuris.memory import load_memory
from recuris.protocol import ProtocolError
from recuris.working import apply_proposal, initialize, invalidate_completions, verifier_digest


def goal(gid="artifact"):
    return {"id": gid, "description": "Required artifact is present and passes its public check",
            "verification": {"command": "python public_check.py", "contains": ["PUBLIC_OK"]}}


def proposal(*updates, new_goals=None, revised=None):
    return {"updates": list(updates), "new_goals": new_goals or [], "revised_verifications": revised or []}


def done(gid="artifact", rid="receipt-1"):
    return {"goal_id": gid, "status": "done", "evidence_ids": [rid], "blocker": ""}


def receipt(state, **changes):
    result = {"kind": "verification", "goal_id": state[0]["id"], "revision": 3,
              "verification_digest": verifier_digest(state[0]["verification"]),
              "completed": True, "exit_code": 0, "synthetic": False, "output": "PUBLIC_OK\n"}
    result.update(changes)
    return result


def test_initialization_binds_checks_and_starts_every_goal_pending():
    payload = {"goals": [goal(), goal("second")]}
    state = initialize(payload, 3)
    assert [item["status"] for item in state] == ["pending", "pending"]
    assert all(item["evidence_ids"] == [] for item in state)
    state[0]["verification"]["contains"].append("changed")
    assert payload["goals"][0]["verification"]["contains"] == ["PUBLIC_OK"]
    with pytest.raises(ProtocolError, match="Duplicate"):
        initialize({"goals": [goal(), goal()]}, 3)
    with pytest.raises(ProtocolError):
        initialize({"goals": []}, 3)


def test_only_matching_current_successful_public_check_can_commit_done():
    state = initialize({"goals": [goal()]}, 3)
    original = deepcopy(state)
    updated, decisions = apply_proposal(state, proposal(done()), {"receipt-1": receipt(state)}, 3, load_memory())
    assert updated[0]["status"] == "done"
    assert updated[0]["evidence_ids"] == ["receipt-1"]
    assert decisions[0]["accepted"] is True
    assert state == original


@pytest.mark.parametrize("changes", [
    {"kind": "terminal"}, {"synthetic": True}, {"exit_code": None}, {"exit_code": True},
    {"exit_code": 1}, {"completed": False}, {"revision": 2}, {"goal_id": "other"},
    {"verification_digest": "old-check"}, {"output": "Only a claim, no success evidence"},
])
def test_forged_stale_failed_or_unrelated_receipts_cannot_commit(changes):
    state = initialize({"goals": [goal()]}, 3)
    updated, decisions = apply_proposal(state, proposal(done()), {"receipt-1": receipt(state, **changes)}, 3, load_memory())
    assert updated[0]["status"] == "pending"
    assert decisions[0]["accepted"] is False


def test_unknown_receipt_and_evolved_output_constraint_block_completion():
    state = initialize({"goals": [goal()]}, 3)
    memory = load_memory()
    updated, decisions = apply_proposal(state, proposal(done(rid="invented")), {}, 3, memory)
    assert updated[0]["status"] == "pending" and not decisions[0]["accepted"]
    memory["C"]["forbidden_output"] = ["ERROR"]
    updated, decisions = apply_proposal(state, proposal(done()), {"receipt-1": receipt(state, output="PUBLIC_OK ERROR")}, 3, memory)
    assert updated[0]["status"] == "pending" and not decisions[0]["accepted"]


def test_revising_a_verifier_requires_new_execution_even_with_old_receipt():
    state = initialize({"goals": [goal()]}, 3)
    checks = {"receipt-1": receipt(state)}
    completed, _ = apply_proposal(state, proposal(done()), checks, 3, load_memory())
    revised = {"goal_id": "artifact", "verification": {"command": "python stronger_check.py", "contains": []}}
    updated, decisions = apply_proposal(completed, proposal(done(), revised=[revised]), checks, 3, load_memory())
    assert updated[0]["status"] == "pending"
    assert updated[0]["evidence_ids"] == []
    assert decisions[0]["accepted"] is False
    assert completed[0]["status"] == "done"


def test_arbitrary_environment_change_reopens_completed_goals_without_mutating_input():
    state = initialize({"goals": [goal()]}, 3)
    completed, _ = apply_proposal(state, proposal(done()), {"receipt-1": receipt(state)}, 3, load_memory())
    reopened = invalidate_completions(completed)
    assert reopened[0]["status"] == "pending"
    assert reopened[0]["evidence_ids"] == []
    assert "recheck" in reopened[0]["blocker"]
    assert completed[0]["status"] == "done"


def test_invalid_proposal_is_atomic_and_cannot_replace_existing_goals():
    state = initialize({"goals": [goal()]}, 3)
    original = deepcopy(state)
    with pytest.raises(ProtocolError, match="replace"):
        apply_proposal(state, proposal(new_goals=[goal()]), {}, 3, load_memory())
    with pytest.raises(ProtocolError, match="blocker"):
        apply_proposal(state, proposal({"goal_id": "artifact", "status": "blocked", "evidence_ids": [], "blocker": ""}), {}, 3, load_memory())
    assert state == original
