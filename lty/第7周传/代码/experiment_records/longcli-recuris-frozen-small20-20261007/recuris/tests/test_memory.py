from copy import deepcopy
import pytest
from recuris.memory import invoke, load_memory, memory_digest, save_memory, unresolved_signature, validate_memory
from recuris.protocol import ProtocolError, parse_action, parse_object


def skill(sid, words):
    return {"id": sid, "description": words, "content": "Observe, fix, then verify.", "tags": []}


def test_neutral_memory_has_no_learned_content_and_is_independent(tmp_path):
    one, two = load_memory(), load_memory()
    assert one["E"] == []
    one["E"].append(skill("example", "build"))
    assert two["E"] == []
    saved = save_memory(one, tmp_path / "memory.json")
    assert load_memory(saved) == one
    assert memory_digest(one) != memory_digest(two)


def test_default_invocation_only_at_first_turn():
    memory = load_memory()
    memory["E"] = [skill("first", "build"), skill("second", "test")]
    assert len(invoke(memory, [], 1, None)) == 2
    assert invoke(memory, [], 2, None) == []


def test_state_retrieval_excludes_solved_goals():
    memory = load_memory()
    memory["E"] = [skill("build", "build compiler"), skill("test", "test correctness")]
    memory["rho"].update(trigger="every_turn", retrieval="lexical")
    goals = [{"id": "g1", "description": "build compiler", "status": "done"},
             {"id": "g2", "description": "test correctness", "status": "pending"}]
    assert [s["id"] for s in invoke(memory, goals, 1, None)] == ["test"]


def test_changed_state_trigger_does_not_fire_for_identical_state():
    memory = load_memory()
    memory["E"] = [skill("test", "check")]
    memory["rho"]["trigger"] = "on_unresolved_change"
    goals = [{"id": "g1", "description": "check", "status": "pending"}]
    assert invoke(memory, goals, 1, None)
    assert not invoke(memory, goals, 2, unresolved_signature(goals))


@pytest.mark.parametrize("mutate", [
    lambda m: m.update(kernel="some code"),
    lambda m: m.update(schema_version=True),
    lambda m: m["E"].extend([skill("dup", "a"), skill("dup", "b")]),
    lambda m: m["rho"].update(trigger="exec_python"),
    lambda m: m["W"].update(max_goals=False),
    lambda m: m["C"].update(require_exit_zero=False),
])
def test_memory_cannot_replace_kernel_or_add_unsupported_fields(mutate):
    memory = load_memory()
    mutate(memory)
    with pytest.raises(ProtocolError):
        validate_memory(memory)


@pytest.mark.parametrize("value", ['{"a":1,"a":2}', '{"value":NaN}', '[]'])
def test_duplicate_keys_and_nonfinite_values_rejected(value):
    with pytest.raises(ProtocolError):
        parse_object(value)


def test_action_never_combines_completion_and_tool_input():
    with pytest.raises(ProtocolError):
        parse_action('{"analysis":"","operation":"finish","keystrokes":"rm something\\n","duration":0,"goal_id":"","final_answer":"done"}')
