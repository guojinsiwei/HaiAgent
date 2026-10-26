"""All outcomes and model replies here are synthetic; no benchmark is run."""

from copy import deepcopy
from dataclasses import asdict
import json
from unittest.mock import patch

import pytest

from recuris.client import ModelClientError, ModelReply
from recuris.evolution import (
    EvolutionError, MetaAgent, apply_component_patches, evaluate_gate,
    pair_scores, prepare_trace, validate_diagnoses,
)
from recuris.memory import memory_digest


def memory():
    return {
        "schema_version": 1, "E": [],
        "W": {"init_guidance": "List requested goals.", "update_guidance": "Use observations.", "max_goals": 12},
        "rho": {"trigger": "first_turn", "retrieval": "all", "max_skills": 8},
        "C": {"required_output": [], "forbidden_output": []},
    }


def skill():
    return {"id": "verify_config", "description": "Verify all edited configuration.",
            "content": "Read back every setting before declaring the goal complete.", "tags": ["configuration"]}


def trace():
    return [{"step_id": 1, "state_before": [], "invoked_skills": [],
             "action": {"command": "cat config"}, "observation": {"output": "missing setting"},
             "proposed_state": {}, "checker_decisions": [], "state_after": [], "event": "turn"}]


def diagnosis(component="E", ids=None):
    return {"component": component, "description": "Missing procedural validation.", "evidence_step_ids": ids or [1]}


def diagnosed(*components):
    return {"diagnoses": [diagnosis(c) for c in (components or ("E",))], "noop_reason": ""}


def patch_e():
    return {"component": "E", "replacement": [skill()]}


class FakeClient:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete(self, messages, *, purpose, deadline_monotonic=None):
        self.calls.append((deepcopy(messages), purpose, deadline_monotonic))
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, ModelReply):
            return value
        return ModelReply(value if isinstance(value, str) else json.dumps(value), 10, 3, "stop")


def row(task="source-1", old=False, new=True, seed=0):
    return {"task_id": task, "seed": seed, "baseline": old, "candidate": new}


def test_tta_proposes_e_only_and_preserves_input_and_other_components():
    base, evidence = memory(), trace()
    before = deepcopy((base, evidence))
    client = FakeClient(diagnosed(), patch_e())
    candidate = MetaAgent(client).propose(base, "Configure the service", evidence)
    assert candidate.changed_components == ["E"]
    assert candidate.candidate_memory["E"] == [skill()]
    assert candidate.base_digest == memory_digest(base)
    assert candidate.candidate_digest == memory_digest(candidate.candidate_memory)
    assert (candidate.model_calls, candidate.input_tokens, candidate.output_tokens) == (2, 20, 6)
    assert candidate.no_op is False
    assert candidate.trace_step_ids == [1]
    assert (base, evidence) == before
    for component in ("W", "rho", "C"):
        assert candidate.candidate_memory[component] == base[component]
    assert json.loads(client.calls[0][0][1]["content"])["official_success"] is False
    assert all(call[2] is not None for call in client.calls)
    assert asdict(candidate)["candidate_memory"]["E"] == [skill()]


def test_noop_uses_localization_only_and_returns_independent_memory():
    base = memory()
    client = FakeClient({"diagnoses": [], "noop_reason": "Failure was outside the memory patch space."})
    candidate = MetaAgent(client).propose(base, "Task", trace())
    assert candidate.no_op and candidate.model_calls == 1
    assert candidate.changed_components == []
    assert candidate.base_digest == candidate.candidate_digest
    candidate.candidate_memory["E"].append(skill())
    assert base["E"] == []


def test_cross_task_patches_each_implicated_component_separately():
    base = memory()
    updated_w = dict(base["W"], update_guidance="Keep unmatched requirements unresolved.")
    client = FakeClient(diagnosed("W", "E"), patch_e(), {"component": "W", "replacement": updated_w})
    candidate = MetaAgent(client).propose(base, "Task", trace(), mode="cross_task")
    assert candidate.changed_components == ["E", "W"]
    assert candidate.model_calls == 3
    assert candidate.candidate_memory["W"] == updated_w
    assert candidate.candidate_memory["rho"] == base["rho"]
    assert candidate.candidate_memory["C"] == base["C"]
    assert [call[1] for call in client.calls] == ["recuris_localization", "recuris_patch_E", "recuris_patch_W"]


def test_tta_rejects_other_component_diagnoses_without_patching():
    client = FakeClient(diagnosed("W"), diagnosed("W"))
    with pytest.raises(EvolutionError, match="TTA only") as error:
        MetaAgent(client).propose(memory(), "Task", trace())
    assert error.value.model_calls == 2
    assert len(client.calls) == 2


def test_diagnosis_repair_and_patch_repair_are_bounded_and_usage_counted():
    client = FakeClient("not json", diagnosed(), {"component": "W", "replacement": {}}, patch_e())
    result = MetaAgent(client).propose(memory(), "Task", trace())
    assert (result.model_calls, result.input_tokens, result.output_tokens) == (4, 40, 12)
    assert "repair_instruction" in json.loads(client.calls[1][0][1]["content"])
    assert "repair_instruction" in json.loads(client.calls[3][0][1]["content"])


def test_duplicate_response_json_key_is_rejected():
    client = FakeClient('{"diagnoses":[],"diagnoses":[],"noop_reason":"No repair"}')
    with pytest.raises(EvolutionError, match="Duplicate JSON key"):
        MetaAgent(client, max_parse_attempts=1).propose(memory(), "Task", trace())


@pytest.mark.parametrize("ids", [[2], [True], [1, 1], ["1"]])
def test_diagnosis_must_cite_visible_typed_unique_steps(ids):
    with pytest.raises(ValueError):
        validate_diagnoses([diagnosis(ids=ids)], [1], mode="tta")


@pytest.mark.parametrize("hidden", ["verifier", "verifier_output", "test_results", "expected_output", "reward", "official_success"])
def test_hidden_fields_rejected_before_any_model_call(hidden):
    client = FakeClient()
    evidence = trace()
    evidence[0]["observation"][hidden] = "private data"
    with pytest.raises(ValueError, match="information contract"):
        MetaAgent(client).propose(memory(), "Task", evidence)
    assert not client.calls


def test_trace_disallows_unfiltered_task_or_result_envelopes():
    evidence = trace()
    evidence[0]["task"] = {"tests": "hidden"}
    with pytest.raises(ValueError, match="schema"):
        prepare_trace(evidence)


def test_trace_rejects_duplicate_steps_empty_trace_and_nonfinite_values():
    for evidence in ([], trace() * 2, [{"step_id": 1, "observation": float("nan")}], [{"step_id": -1}]):
        with pytest.raises(ValueError):
            prepare_trace(evidence)


def test_trace_preserves_actor_visible_test_command_text_and_detaches_input():
    evidence = trace()
    evidence[0]["action"]["command"] = "pytest tests/test_service.py"
    result = prepare_trace(evidence)
    assert result == evidence
    result[0]["observation"]["output"] = "changed"
    assert result != evidence


def test_context_trimming_preserves_whole_steps_and_tracks_omissions():
    evidence = trace()
    evidence[0]["observation"]["output"] = "x" * 20000
    second = deepcopy(trace()[0])
    second["step_id"] = 2
    evidence.append(second)
    client = FakeClient({"diagnoses": [diagnosis(ids=[2])], "noop_reason": ""}, patch_e())
    candidate = MetaAgent(client, max_context_chars=7000).propose(memory(), "Task", evidence)
    assert candidate.trace_step_ids == [2] and candidate.omitted_step_ids == [1]
    sent = json.loads(client.calls[0][0][1]["content"])
    assert sent["trace"] == [second]
    assert sent["omitted_step_ids"] == [1]
    assert evidence[0]["observation"]["output"] == "x" * 20000


def test_unfit_context_fails_without_model_request():
    client = FakeClient()
    with pytest.raises(EvolutionError, match="context budget"):
        MetaAgent(client, max_context_chars=20).propose(memory(), "Task", trace())
    assert not client.calls


def test_call_budget_counts_localization_and_patch_calls():
    client = FakeClient(diagnosed())
    with pytest.raises(EvolutionError, match="model-call budget") as error:
        MetaAgent(client, max_model_calls=1).propose(memory(), "Task", trace())
    assert (error.value.model_calls, error.value.input_tokens) == (1, 10)


def test_transport_failure_reports_partial_usage_and_no_candidate():
    client = FakeClient(diagnosed(), ModelClientError("offline error", input_tokens=7, output_tokens=2))
    with pytest.raises(EvolutionError, match="offline error") as error:
        MetaAgent(client).propose(memory(), "Task", trace())
    assert (error.value.model_calls, error.value.input_tokens, error.value.output_tokens) == (2, 17, 5)


def test_late_reply_counts_usage_and_is_not_accepted():
    client = FakeClient(diagnosed())
    with patch("recuris.evolution.time.monotonic", side_effect=[0, 0, 601]):
        with pytest.raises(EvolutionError, match="after reply") as error:
            MetaAgent(client).propose(memory(), "Task", trace())
    assert (error.value.input_tokens, error.value.model_calls) == (10, 1)


def test_incomplete_reply_is_retried_even_when_json_is_valid():
    client = FakeClient(ModelReply(json.dumps(diagnosed()), 1, 2, "length"), diagnosed(), patch_e())
    result = MetaAgent(client).propose(memory(), "Task", trace())
    assert (result.model_calls, result.input_tokens, result.output_tokens) == (3, 21, 8)


@pytest.mark.parametrize("kwargs", [
    {"max_model_calls": 0}, {"max_model_calls": True}, {"max_parse_attempts": -1},
    {"max_context_chars": 1.5}, {"max_total_seconds": float("nan")}, {"max_total_seconds": False},
])
def test_invalid_budget_configuration(kwargs):
    with pytest.raises(ValueError):
        MetaAgent(FakeClient(), **kwargs)


def test_noop_cannot_have_fabricated_diagnosis_or_blank_reason():
    for response in ({"diagnoses": [], "noop_reason": ""}, {"diagnoses": [diagnosis()], "noop_reason": "actually no change"}):
        with pytest.raises(EvolutionError):
            MetaAgent(FakeClient(response), max_parse_attempts=1).propose(memory(), "Task", trace())


@pytest.mark.parametrize("patches", [{}, {"E": [], "W": {}}, {"E": []}])
def test_patch_scope_must_exactly_match_actual_diagnosed_changes(patches):
    with pytest.raises(ValueError):
        apply_component_patches(memory(), [diagnosis()], patches, trace_step_ids=[1], mode="tta")


def test_invalid_replacement_is_not_installed():
    original = memory()
    bad = dict(skill(), executable_code="print('must not run')")
    with pytest.raises(ValueError):
        apply_component_patches(original, [diagnosis()], {"E": [bad]}, trace_step_ids=[1], mode="tta")
    assert original["E"] == []


def test_empty_patch_is_explicit_noop():
    base = memory()
    result = apply_component_patches(base, [], {}, trace_step_ids=[1], mode="tta")
    assert result == base and result is not base


def test_gate_accepts_all_repaired_source_and_preserved_anchors():
    sources = [row(seed=1), row(seed=2)]
    development = [row("anchor", True, True), row("other", False, True)]
    before = deepcopy((sources, development))
    result = evaluate_gate(sources, development, test_task_ids=["held-out"])
    assert result.accepted and result.source_repaired == 2
    assert result.dev_baseline_rate == 0.5 and result.dev_candidate_rate == 1
    assert result.anchor_count == 1 and result.anchor_regressions == 0
    assert "engineering_choice" in result.policy
    assert (sources, development) == before


def test_gate_rejects_anchor_regression_even_if_aggregate_improves():
    development = [row("anchor", True, False), row("new-1", False, True), row("new-2", False, True)]
    result = evaluate_gate([row()], development)
    assert not result.accepted
    assert result.reasons == ("previously_passing_anchor_regressed",)


def test_gate_rejects_unrepaired_source_and_source_with_no_actual_improvement():
    anchor = [row("dev", True, True)]
    assert not evaluate_gate([row(new=False)], anchor).accepted
    assert not evaluate_gate([row(old=True)], anchor).accepted


def test_gate_requires_a_repaired_pair_for_each_source_task():
    result = evaluate_gate([row(), row("already-passing", True, True)], [row("dev", True, True)])
    assert result.reasons == ("source_task_without_any_repaired_attempt",)


def test_gate_rejects_mean_regression_and_missing_passing_anchors():
    result = evaluate_gate([row()], [row("dev", True, False)])
    assert set(result.reasons) == {"previously_passing_anchor_regressed", "development_mean_decreased"}
    result = evaluate_gate([row()], [row("dev", False, True)])
    assert result.reasons == ("development_set_has_no_passing_anchors",)


@pytest.mark.parametrize("invalid", [None, 0, 1, 0.0, "false", "error", float("nan")])
def test_gate_never_coerces_invalid_scores_to_failure(invalid):
    with pytest.raises(ValueError, match="exact booleans"):
        evaluate_gate([row(old=invalid)], [row("dev", True, True)])


def test_gate_rejects_missing_scores_unknown_fields_duplicates_empty_dev():
    invalid_sets = [
        [{"task_id": "a", "seed": 0, "baseline": False}],
        [dict(row(), test=True)], [row(), row()], [],
    ]
    for source in invalid_sets:
        with pytest.raises(ValueError):
            evaluate_gate(source, [row("dev", True, True)])
    with pytest.raises(ValueError):
        evaluate_gate([row()], [])


def test_gate_forbids_task_overlap_even_with_different_seeds():
    with pytest.raises(ValueError, match="disjoint"):
        evaluate_gate([row()], [row("source-1", True, True, seed=2)])
    for forbidden in ("source-1", "dev"):
        with pytest.raises(ValueError, match="disjoint"):
            evaluate_gate([row()], [row("dev", True, True)], test_task_ids=[forbidden])


@pytest.mark.parametrize("seed", [True, -1, 1.0, "0", None])
def test_gate_requires_exact_nonnegative_integer_seed(seed):
    with pytest.raises(ValueError):
        evaluate_gate([row(seed=seed)], [row("dev", True, True)])


def test_pair_scores_matches_by_task_and_seed_not_list_order():
    old = [{"task_id": "a", "seed": 0, "success": False}, {"task_id": "a", "seed": 1, "success": True}]
    new = [{"task_id": "a", "seed": 1, "success": True}, {"task_id": "a", "seed": 0, "success": True}]
    assert pair_scores(old, new) == [row("a", seed=0), row("a", True, True, seed=1)]


def test_pair_scores_rejects_missing_seed_duplicate_and_invalid_value():
    old = [{"task_id": "a", "seed": 0, "success": False}]
    for new in ([{"task_id": "a", "seed": 1, "success": True}], old * 2,
                [{"task_id": "a", "seed": 0, "success": None}]):
        with pytest.raises(ValueError):
            pair_scores(old, new)
