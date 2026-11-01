"""Admission verification with stubbed sealed-attempt readers, never real tb."""

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

import pytest

import recuris.admission as admission
from recuris.evolution import Candidate
from recuris.memory import load_memory, memory_digest, save_memory
from recuris.tta import AttemptError


def base_memory():
    return {"schema_version": 1, "E": [],
            "W": {"init_guidance": "Track goals", "update_guidance": "Use evidence", "max_goals": 8},
            "rho": {"trigger": "first_turn", "retrieval": "all", "max_skills": 8},
            "C": {"required_output": [], "forbidden_output": []}}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def make_attempt(task, memory, name, success):
    digest = memory_digest(memory)
    return {
        "success": success, "official_success": success, "task_id": task,
        "memory_digest": digest, "memory": deepcopy(memory), "instruction": "Public task",
        "trace": [{"step_id": 1, "observation": {"output": "visible evidence"}, "event": "turn"}],
        "run_id": name, "trial_name": task + ".1-of-1." + name,
        "provenance": {
            "schema_version": 1, "benchmark_commit": "pinned", "task_id": task,
            "task_sha256": "task-hash-" + task, "model_name": "offline-model",
            "agent_import_path": "recuris.longcli:RecurisAgent", "agent_options": [],
            "endpoint_environment": {}, "memory_digest": digest, "adapter_code_digest": "fixed-code",
            "harness_timeout_seconds": 3900, "process_timeout_seconds": 4500,
            "n_attempts": 1, "give_test_output": 1,
        },
    }


class Inputs:
    def __init__(self, tmp_path, monkeypatch):
        self.root = tmp_path
        self.base = base_memory()
        self.new = deepcopy(self.base)
        self.new["E"] = [{"id": "check", "description": "Check requirements", "content": "Read back all requested fields.", "tags": []}]
        self.candidate = asdict(Candidate(
            diagnoses=[{"component": "E", "description": "Missing validation", "evidence_step_ids": [1]}],
            base_digest=memory_digest(self.base), candidate_memory=self.new,
            changed_components=["E"], candidate_digest=memory_digest(self.new), mode="cross_task",
            input_tokens=50, output_tokens=30, model_calls=2, trace_step_ids=[1],
        ))
        self.candidate.update(source_task_id="source", source_attempt_dir="failed-source")
        self.split = {"evolve": ["source", "other-evolve"], "dev": ["dev-anchor", "dev-other"],
                      "test": ["unseen-test"], "seeds": [0, 1]}
        self.attempts = {(tmp_path / "failed-source").resolve(): make_attempt("source", self.base, "source-original", False)}
        self.evaluations = {"base_digest": memory_digest(self.base), "candidate_digest": memory_digest(self.new), "source": [], "dev": []}
        for split_name, tasks in (("source", ["source"]), ("dev", self.split["dev"])):
            for task in tasks:
                for seed in self.split["seeds"]:
                    row = {"task_id": task, "seed": seed}
                    for variant, memory in (("baseline", self.base), ("candidate", self.new)):
                        name = f"{task}-{seed}-{variant}"
                        row[variant + "_attempt_dir"] = name
                        success = task.startswith("dev") or variant == "candidate"
                        self.attempts[(tmp_path / name).resolve()] = make_attempt(task, memory, name, success)
                    self.evaluations[split_name].append(row)
        self.read_calls = []

        def reader(directory):
            path = Path(directory).resolve()
            self.read_calls.append(path)
            value = self.attempts[path]
            if isinstance(value, Exception):
                raise value
            return deepcopy(value)

        monkeypatch.setattr(admission, "read_attempt", reader)

    def save(self):
        save_memory(self.base, self.root / "base.json")
        write(self.root / "candidate.json", self.candidate)
        write(self.root / "evaluations.json", self.evaluations)
        write(self.root / "split.json", self.split)

    def run(self):
        self.save()
        return admission.admit_candidate(self.root / "base.json", self.root / "candidate.json",
                                         self.root / "evaluations.json", self.root / "split.json", self.root / "admitted")

    def fail(self, match=None):
        with pytest.raises((ValueError, AttemptError), match=match):
            self.run()
        assert not (self.root / "admitted").exists()


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    return Inputs(tmp_path, monkeypatch)


def test_accepts_sealed_complete_pairs_and_persists_candidate(inputs):
    result = inputs.run()
    assert result["accepted"] is True
    assert result["source_count"] == 2 and result["dev_count"] == 4
    assert result["replicate_indices"] == [0, 1] and result["deterministic_model_seeds"] is False
    assert load_memory(inputs.root / "admitted" / "memory.json") == inputs.new
    saved = json.loads((inputs.root / "admitted" / "gate.json").read_text(encoding="utf-8"))
    assert saved == result
    assert result["deployed_digest"] == memory_digest(inputs.new)
    assert len(inputs.read_calls) == 13
    assert not any("unseen-test" in str(path) for path in inputs.read_calls)


def test_rejection_preserves_base_bytes_and_records_reason(inputs):
    path = inputs.root / inputs.evaluations["dev"][0]["candidate_attempt_dir"]
    inputs.attempts[path]["success"] = False
    inputs.attempts[path]["official_success"] = False
    result = inputs.run()
    assert not result["accepted"]
    assert "previously_passing_anchor_regressed" in result["reasons"]
    assert (inputs.root / "admitted" / "memory.json").read_bytes() == (inputs.root / "base.json").read_bytes()
    assert result["deployed_digest"] == memory_digest(inputs.base)


@pytest.mark.parametrize("field", ["base_digest", "candidate_digest"])
def test_candidate_digest_mismatch_fails_before_output(inputs, field):
    inputs.candidate[field] = "wrong"
    inputs.fail("digest mismatch")


@pytest.mark.parametrize("field", ["base_digest", "candidate_digest"])
def test_evaluation_digest_mismatch_fails(inputs, field):
    inputs.evaluations[field] = "wrong"
    inputs.fail("manifest memory digests")


def test_rejects_tta_candidate(inputs):
    inputs.candidate["mode"] = "tta"
    inputs.fail("cross_task")


def test_rejects_candidate_not_from_frozen_evolve_split(inputs):
    inputs.split["evolve"] = ["another"]
    inputs.fail("frozen evolve")


def test_requires_source_attempt_official_failure(inputs):
    source = inputs.attempts[inputs.root / "failed-source"]
    source["success"] = source["official_success"] = True
    inputs.fail("official failure")


@pytest.mark.parametrize("value", [None, 0, "false"])
def test_does_not_coerce_source_outcome(inputs, value):
    inputs.attempts[inputs.root / "failed-source"]["success"] = value
    inputs.fail("boolean")


def test_source_identity_must_match_candidate(inputs):
    source = inputs.attempts[inputs.root / "failed-source"]
    source["task_id"] = "another"
    inputs.fail("task or memory")


@pytest.mark.parametrize("value", [["W"], ["E", "W"], [], ["E", "E"]])
def test_changed_components_rechecked_from_actual_content(inputs, value):
    inputs.candidate["changed_components"] = value
    inputs.fail("changed_components")


def test_component_scope_rechecked_even_when_digests_are_recomputed(inputs):
    inputs.candidate["candidate_memory"]["W"]["max_goals"] = 10
    inputs.candidate["candidate_digest"] = memory_digest(inputs.candidate["candidate_memory"])
    inputs.candidate["changed_components"] = ["E", "W"]
    inputs.fail("component set")


def test_diagnosis_must_reference_real_visible_source_steps(inputs):
    inputs.candidate["diagnoses"][0]["evidence_step_ids"] = [2]
    inputs.fail("unseen trace")


@pytest.mark.parametrize("visible,omitted", [([2], []), ([True], []), ([1], [1]), ([], [1])])
def test_trace_partition_cannot_be_fabricated(inputs, visible, omitted):
    inputs.candidate["trace_step_ids"] = visible
    inputs.candidate["omitted_step_ids"] = omitted
    inputs.fail("source steps|prefix/suffix")


def test_trace_partition_accepts_real_recorded_truncation(inputs):
    inputs.attempts[inputs.root / "failed-source"]["trace"].insert(0, {"step_id": 0, "event": "initialize"})
    inputs.candidate["omitted_step_ids"] = [0]
    assert inputs.run()["accepted"]


def test_noop_flag_and_metadata_are_not_trusted(inputs):
    inputs.candidate["no_op"] = True
    inputs.fail("no_op")


@pytest.mark.parametrize("name,value", [("input_tokens", -1), ("model_calls", True), ("elapsed_seconds", -1), ("reason", "contradiction")])
def test_candidate_metadata_validation(inputs, name, value):
    inputs.candidate[name] = value
    inputs.fail()


@pytest.mark.parametrize("field", ["source", "dev"])
def test_missing_pair_on_both_sides_is_rejected_against_split_manifest(inputs, field):
    inputs.evaluations[field].pop()
    inputs.fail("matrix")


def test_source_matrix_cannot_include_other_evolve_task(inputs):
    inputs.evaluations["source"][0]["task_id"] = "other-evolve"
    inputs.fail("matrix")


def test_gate_cannot_read_test_task_attempts(inputs):
    inputs.evaluations["dev"][0]["task_id"] = "unseen-test"
    inputs.fail("matrix")
    assert len(inputs.read_calls) == 1


def test_scores_cannot_be_substituted_for_sealed_attempt_directories(inputs):
    inputs.evaluations["source"][0]["baseline"] = False
    inputs.fail("requires exactly")


def test_unknown_evaluation_fields_rejected(inputs):
    inputs.evaluations["test"] = []
    inputs.fail("requires exactly")


@pytest.mark.parametrize("mutate", [
    lambda split: split["dev"].append("source"),
    lambda split: split["test"].append("dev-anchor"),
    lambda split: split["evolve"].append("source"),
    lambda split: split.update(seeds=[0, 0]),
    lambda split: split.update(seeds=[True]),
    lambda split: split.update(seeds=[]),
    lambda split: split.update(dev=[]),
])
def test_split_validation(inputs, mutate):
    mutate(inputs.split)
    inputs.fail()


def test_reusing_attempt_directory_for_another_replicate_fails(inputs):
    inputs.evaluations["source"][1]["baseline_attempt_dir"] = inputs.evaluations["source"][0]["baseline_attempt_dir"]
    inputs.fail("directory cannot be reused")


def test_copying_attempt_to_new_directory_does_not_create_new_replicate(inputs):
    first = inputs.root / inputs.evaluations["source"][0]["baseline_attempt_dir"]
    second = inputs.root / inputs.evaluations["source"][1]["baseline_attempt_dir"]
    inputs.attempts[second] = deepcopy(inputs.attempts[first])
    inputs.fail("copied and reused")


def test_original_failure_may_also_be_one_baseline_replicate(inputs):
    inputs.evaluations["source"][0]["baseline_attempt_dir"] = "failed-source"
    assert inputs.run()["accepted"]


@pytest.mark.parametrize("field,value", [
    ("model_name", "different"), ("adapter_code_digest", "different"),
    ("harness_timeout_seconds", 4000), ("agent_options", [{"name": "max_steps", "value": 5}]),
    ("endpoint_environment", {"OPENAI_BASE_URL": "different"}),
])
def test_model_code_and_budget_changes_are_rejected(inputs, field, value):
    path = inputs.root / inputs.evaluations["dev"][0]["candidate_attempt_dir"]
    inputs.attempts[path]["provenance"][field] = value
    inputs.fail("model/code/budget")


def test_matched_pair_cannot_silently_use_a_different_global_model(inputs):
    for variant in ("baseline", "candidate"):
        path = inputs.root / inputs.evaluations["dev"][0][variant + "_attempt_dir"]
        inputs.attempts[path]["provenance"]["model_name"] = "different-model"
    inputs.fail("model/code/budget")


def test_paired_task_hash_must_match(inputs):
    path = inputs.root / inputs.evaluations["dev"][0]["candidate_attempt_dir"]
    inputs.attempts[path]["provenance"]["task_sha256"] = "different-task"
    inputs.fail("identical provenance|match exactly")


def test_same_task_cannot_change_between_replicates(inputs):
    for variant in ("baseline", "candidate"):
        path = inputs.root / inputs.evaluations["dev"][1][variant + "_attempt_dir"]
        inputs.attempts[path]["provenance"]["task_sha256"] = "different-task"
    inputs.fail("identical provenance")


def test_read_attempt_hash_or_official_result_error_never_becomes_failure(inputs):
    path = inputs.root / inputs.evaluations["dev"][0]["baseline_attempt_dir"]
    inputs.attempts[path] = AttemptError("official outcome is missing")
    inputs.fail("official outcome")


def test_wrong_memory_evaluation_cannot_be_used(inputs):
    path = inputs.root / inputs.evaluations["dev"][0]["candidate_attempt_dir"]
    inputs.attempts[path]["memory_digest"] = memory_digest(inputs.base)
    inputs.fail("task or memory")


def test_incomplete_provenance_cannot_pass_by_equality(inputs):
    inputs.attempts[inputs.root / "failed-source"]["provenance"] = {}
    inputs.fail("lacks required")


def test_existing_output_directory_is_never_overwritten(inputs):
    output = inputs.root / "admitted"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("unchanged")
    with pytest.raises(FileExistsError):
        inputs.run()
    assert sentinel.read_text() == "unchanged"
    assert not inputs.read_calls


def test_noop_candidate_is_recorded_but_not_admitted(inputs):
    digest = memory_digest(inputs.base)
    inputs.candidate.update(diagnoses=[], candidate_memory=deepcopy(inputs.base), candidate_digest=digest,
                            changed_components=[], no_op=True, reason="No useful memory repair")
    inputs.evaluations["candidate_digest"] = digest
    for rows in (inputs.evaluations["source"], inputs.evaluations["dev"]):
        for row in rows:
            attempt = inputs.attempts[inputs.root / row["candidate_attempt_dir"]]
            attempt["memory_digest"] = digest
            attempt["memory"] = deepcopy(inputs.base)
            attempt["provenance"]["memory_digest"] = digest
    result = inputs.run()
    assert result["accepted"] is False
    assert "no_op_candidate_has_no_memory_change" in result["reasons"]
