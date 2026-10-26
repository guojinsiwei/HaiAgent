"""Admit a cross-task candidate only from paired, sealed official attempts.

No evaluations or model calls run here. Artifact hashes detect accidental changes
and consistency errors, not deliberate forgery by someone controlling the files.
The ``seed`` fields below are replicate indices, not deterministic model seeds.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, fields
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from .evolution import Candidate, apply_component_patches, evaluate_gate
from .memory import COMPONENTS, load_memory, memory_digest, save_memory, validate_memory
from .protocol import exact_keys, parse_object
from .tta import read_attempt


_PROVENANCE_FIELDS = {
    "schema_version", "benchmark_commit", "task_id", "task_sha256", "model_name",
    "agent_import_path", "agent_options", "endpoint_environment", "memory_digest",
    "adapter_code_digest", "harness_timeout_seconds", "process_timeout_seconds",
    "n_attempts", "give_test_output",
}


def _read(path: Path) -> dict:
    return parse_object(path.read_text(encoding="utf-8-sig"))


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(label + " must be a non-empty string")
    return value


def _path(value: Any, relative_to: Path) -> Path:
    path = Path(_text(value, "attempt directory"))
    return (path if path.is_absolute() else relative_to / path).resolve()


def _split(value: dict) -> dict:
    exact_keys(value, {"evolve", "dev", "test", "seeds"}, "split")
    seen = set()
    for name in ("evolve", "dev", "test"):
        entries = value[name]
        if not isinstance(entries, list) or (name in {"evolve", "dev"} and not entries):
            raise ValueError("evolve and dev must be non-empty task lists; test must be a task list")
        for item in entries:
            _text(item, name + " task ID")
            if item in seen:
                raise ValueError("split task IDs must be unique and disjoint across evolve/dev/test")
            seen.add(item)
    seeds = value["seeds"]
    if (not isinstance(seeds, list) or not seeds
            or any(type(item) is not int or item < 0 for item in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError("seeds must be unique non-negative integer replicate indices")
    return deepcopy(value)


def _provenance(attempt: dict) -> dict:
    value = attempt.get("provenance")
    if not isinstance(value, dict) or not _PROVENANCE_FIELDS <= set(value):
        raise ValueError("attempt provenance lacks required model/code/task/budget fields")
    if value["task_id"] != attempt.get("task_id") or value["memory_digest"] != attempt.get("memory_digest"):
        raise ValueError("attempt identity or memory differs from its provenance")
    return value


def _signature(attempt: dict, *, across_tasks: bool) -> dict:
    excluded = {"memory_digest"}
    if across_tasks:
        excluded.update({"task_id", "task_sha256"})
    return {key: value for key, value in _provenance(attempt).items() if key not in excluded}


def _validate_attempt(attempt: dict, *, task_id: str, digest: str) -> None:
    if not isinstance(attempt, dict) or type(attempt.get("success")) is not bool:
        raise ValueError("attempt must expose one validated official boolean outcome")
    if attempt.get("task_id") != task_id or attempt.get("memory_digest") != digest:
        raise ValueError("attempt task or memory digest does not match evaluation assignment")
    if "official_success" in attempt and (type(attempt["official_success"]) is not bool
                                          or attempt["official_success"] != attempt["success"]):
        raise ValueError("attempt outcome fields disagree")
    _provenance(attempt)


def _identity(attempt: dict) -> tuple[str, str]:
    # A copied attempt directory retains the same validated run/trial identity.
    return (_text(attempt.get("run_id"), "attempt run_id"),
            _text(attempt.get("trial_name"), "attempt trial_name"))


def _validate_candidate(candidate: dict, base: dict, source: dict) -> dict:
    expected = {item.name for item in fields(Candidate)} | {"source_task_id", "source_attempt_dir"}
    exact_keys(candidate, expected, "candidate")
    if candidate["mode"] != "cross_task":
        raise ValueError("admission accepts cross_task candidates only")
    proposed = validate_memory(candidate["candidate_memory"])
    if candidate["base_digest"] != memory_digest(base) or candidate["candidate_digest"] != memory_digest(proposed):
        raise ValueError("candidate base or candidate memory digest mismatch")
    visible, omitted = candidate["trace_step_ids"], candidate["omitted_step_ids"]
    original_ids = [step["step_id"] for step in source["trace"]]
    if not isinstance(visible, list) or not isinstance(omitted, list) or not visible:
        raise ValueError("candidate must record its visible and omitted source steps")
    # JSON encodes true == 1 in Python; typed equality prevents fabricated IDs.
    key = lambda value: (type(value).__name__, value)
    if [key(x) for x in omitted + visible] != [key(x) for x in original_ids]:
        raise ValueError("candidate trace selection is not the source trace's recorded prefix/suffix partition")
    changed = sorted(component for component in COMPONENTS if base[component] != proposed[component])
    if candidate["changed_components"] != changed:
        raise ValueError("candidate changed_components contradicts the actual memory changes")
    patches = {component: proposed[component] for component in changed}
    rebuilt = apply_component_patches(base, candidate["diagnoses"], patches,
                                      trace_step_ids=visible, mode="cross_task")
    if rebuilt != proposed:
        raise ValueError("candidate modifies something outside its diagnosed components")
    if type(candidate["no_op"]) is not bool or candidate["no_op"] != (not changed):
        raise ValueError("candidate no_op flag contradicts its changes")
    reason = candidate["reason"]
    if not isinstance(reason, str) or (not changed and not reason.strip()) or (changed and reason):
        raise ValueError("candidate reason must describe only a no-op")
    for name in ("input_tokens", "output_tokens", "model_calls"):
        if type(candidate[name]) is not int or candidate[name] < 0:
            raise ValueError("candidate usage counts must be non-negative integers")
    elapsed = candidate["elapsed_seconds"]
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("candidate elapsed_seconds must be finite and non-negative")
    return proposed


def _evaluation_rows(rows: Any, *, tasks: set[str], seeds: list[int], label: str) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError(label + " evaluations must be a list")
    found = set()
    for row in rows:
        exact_keys(row, {"task_id", "seed", "baseline_attempt_dir", "candidate_attempt_dir"}, label + " evaluation")
        task = _text(row["task_id"], "evaluation task_id")
        if type(row["seed"]) is not int or row["seed"] < 0:
            raise ValueError("evaluation seed must be an integer replicate index")
        pair = (task, row["seed"])
        if pair in found:
            raise ValueError("duplicate evaluation task/replicate pair")
        found.add(pair)
    expected = {(task, seed) for task in tasks for seed in seeds}
    if found != expected:
        raise ValueError(label + " evaluations do not exactly cover the predeclared task/replicate matrix")
    return rows


def admit_candidate(base_memory_path: str | Path, candidate_path: str | Path,
                    evaluations_path: str | Path, split_path: str | Path,
                    output_dir: str | Path) -> dict:
    """Validate official attempts, decide the gate, and write a fresh result dir.

    Relative ``source_attempt_dir`` resolves against the candidate JSON directory;
    evaluation attempt paths resolve against the evaluations JSON directory.
    Any consistency failure raises without creating ``output_dir``. A legitimate
    gate rejection writes gate.json and the original base memory.json unchanged.
    Split JSON: {evolve:[str], dev:[str], test:[str], seeds:[int]}.
    Evaluations JSON: {base_digest, candidate_digest, source:[paired paths],
    dev:[paired paths]}. Paired paths are {task_id, seed, baseline_attempt_dir,
    candidate_attempt_dir}; callers cannot supply boolean gate scores directly.
    """
    base_path = Path(base_memory_path).resolve()
    proposal_path = Path(candidate_path).resolve()
    evidence_path = Path(evaluations_path).resolve()
    manifest_path = Path(split_path).resolve()
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise FileExistsError("admission output directory already exists")
    base = load_memory(base_path)
    base_hash = memory_digest(base)
    candidate = _read(proposal_path)
    split = _split(_read(manifest_path))
    source_task = _text(candidate.get("source_task_id"), "candidate source_task_id")
    if source_task not in split["evolve"]:
        raise ValueError("candidate source task must belong to the frozen evolve split")
    source_path = _path(candidate.get("source_attempt_dir"), proposal_path.parent)
    source_attempt = read_attempt(source_path)
    _validate_attempt(source_attempt, task_id=source_task, digest=base_hash)
    if source_attempt["success"]:
        raise ValueError("candidate source attempt must be an official failure")
    proposed = _validate_candidate(candidate, base, source_attempt)
    proposed_hash = memory_digest(proposed)
    evaluations = _read(evidence_path)
    exact_keys(evaluations, {"base_digest", "candidate_digest", "source", "dev"}, "evaluations")
    if evaluations["base_digest"] != base_hash or evaluations["candidate_digest"] != proposed_hash:
        raise ValueError("evaluation manifest memory digests do not match this candidate")
    _evaluation_rows(evaluations["source"], tasks={source_task}, seeds=split["seeds"], label="source")
    _evaluation_rows(evaluations["dev"], tasks=set(split["dev"]), seeds=split["seeds"], label="dev")
    global_signature = _signature(source_attempt, across_tasks=True)
    task_signatures = {source_task: _signature(source_attempt, across_tasks=False)}
    used_paths: set[Path] = set()
    used_identities: set[tuple[str, str]] = set()
    scored: dict[str, list[dict]] = {"source": [], "dev": []}
    audited: dict[str, list[dict]] = {"source": [], "dev": []}
    for split_name in ("source", "dev"):
        for row in evaluations[split_name]:
            pair = {}
            resolved_paths = {}
            for variant, digest in (("baseline", base_hash), ("candidate", proposed_hash)):
                path = _path(row[variant + "_attempt_dir"], evidence_path.parent)
                if path in used_paths:
                    raise ValueError("an attempt directory cannot be reused across evaluation pairs or variants")
                attempt = read_attempt(path)
                _validate_attempt(attempt, task_id=row["task_id"], digest=digest)
                identity = _identity(attempt)
                if identity in used_identities:
                    raise ValueError("the same sealed run/trial cannot be copied and reused as another replicate")
                used_paths.add(path)
                used_identities.add(identity)
                if _signature(attempt, across_tasks=True) != global_signature:
                    raise ValueError("all proposal/evaluation attempts must use the same model/code/budget provenance")
                task_signature = _signature(attempt, across_tasks=False)
                if row["task_id"] in task_signatures and task_signatures[row["task_id"]] != task_signature:
                    raise ValueError("the same task must retain identical provenance across all replicates")
                task_signatures[row["task_id"]] = task_signature
                pair[variant] = attempt
                resolved_paths[variant + "_attempt_dir"] = str(path)
            if _signature(pair["baseline"], across_tasks=False) != _signature(pair["candidate"], across_tasks=False):
                raise ValueError("paired attempt provenance must match exactly except for memory_digest")
            # The source task's public task file must also match the failure
            # that was diagnosed, including for later replicate evaluations.
            if row["task_id"] == source_task and _signature(pair["baseline"], across_tasks=False) != _signature(source_attempt, across_tasks=False):
                raise ValueError("source evaluation task differs from the diagnosed source attempt")
            values = {"task_id": row["task_id"], "seed": row["seed"],
                      "baseline": pair["baseline"]["success"], "candidate": pair["candidate"]["success"]}
            scored[split_name].append(values)
            audited[split_name].append({**values, **resolved_paths,
                                       "baseline_run_id": pair["baseline"]["run_id"],
                                       "candidate_run_id": pair["candidate"]["run_id"]})
    gate = asdict(evaluate_gate(scored["source"], scored["dev"], test_task_ids=split["test"]))
    if candidate["no_op"]:
        gate["accepted"] = False
        gate["reasons"] = [*gate["reasons"], "no_op_candidate_has_no_memory_change"]
    # Use JSON types in the returned object and the persisted report alike.
    gate["reasons"] = list(gate["reasons"])
    result = {
        **gate, "schema_version": 1, "base_digest": base_hash, "candidate_digest": proposed_hash,
        "deployed_digest": proposed_hash if gate["accepted"] else base_hash,
        "source_task_id": source_task, "source_attempt_dir": str(source_path),
        "replicate_indices": split["seeds"], "deterministic_model_seeds": False,
        "split": split, "evidence": audited,
        "input_artifact_hashes": {"base_memory": sha256(base_path.read_bytes()).hexdigest(),
                                  "candidate": sha256(proposal_path.read_bytes()).hexdigest(),
                                  "evaluations": sha256(evidence_path.read_bytes()).hexdigest(),
                                  "split": sha256(manifest_path.read_bytes()).hexdigest()},
        "integrity_scope": "local_hash_consistency_not_cryptographic_authentication",
    }
    destination.mkdir(parents=True, exist_ok=False)
    if gate["accepted"]:
        save_memory(proposed, destination / "memory.json")
    else:
        (destination / "memory.json").write_bytes(base_path.read_bytes())
    (destination / "gate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result
