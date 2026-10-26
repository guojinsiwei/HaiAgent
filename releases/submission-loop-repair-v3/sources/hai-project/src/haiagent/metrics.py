"""Outcome import and contextual redundancy audit. No mechanical-repeat proxy."""
import hashlib
import json
from pathlib import Path
from statistics import mean

from .storage import atomic_json, digest, read_trace
from .evaluation import source_success

REDUNDANT_CATEGORIES = {"equivalent_information", "known_unchanged_blocker", "unnecessary_reverification", "irrelevant_to_goal", "other_no_increment"}


def load_run(directory):
    directory = Path(directory)
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    raw = (directory / "events.jsonl").read_bytes()
    if result.get("trace_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("Run result does not match trace")
    rows = read_trace(directory / "events.jsonl")
    if rows[-1]["event"] != "run_end" or rows[0]["run_id"] != result["run_id"]:
        raise ValueError("Incomplete/mismatched run")
    recorded_result = rows[-1].get("result", {})
    if {k: v for k, v in result.items() if k != "trace_sha256"} != recorded_result:
        raise ValueError("Result metadata altered relative to trace")
    artifact = result.get("artifact")
    if result.get("submitted"):
        if not isinstance(artifact, dict):
            raise ValueError("Submitted artifact missing")
        if artifact.get("kind") == "git_patch":
            target = (directory / artifact["path"]).resolve()
            if not target.is_relative_to(directory.resolve()) or not target.is_file():
                raise ValueError("Missing/invalid patch path")
            if hashlib.sha256(target.read_bytes()).hexdigest() != artifact["sha256"]:
                raise ValueError("Artifact checksum mismatch")
        elif artifact.get("kind") == "terminal":
            saved = json.loads((directory / "terminal-submission.json").read_text(encoding="utf-8"))
            if saved != artifact or digest({k: v for k, v in saved.items() if k != "sha256"}) != artifact["sha256"]:
                raise ValueError("Terminal artifact checksum mismatch")
        else:
            raise ValueError("Unknown artifact kind")
    return result, rows


def prepare_audit(directory, destination):
    result, rows = load_run(directory)
    starts = [r for r in rows if r["event"] == "tool_start"]
    ends = {r["call_id"]: r for r in rows if r["event"] == "tool_end"}
    bundle = {"schema": "hai-contextual-audit-v1", "run_id": result["run_id"],
              "trace_sha256": result["trace_sha256"], "reviewer": "",
              "rubric": "Judge avoidability from information visible BEFORE the call. Failure, later failure to solve, or matching command text alone is not redundancy. New evidence, changed preconditions, a genuine validation obligation, or uncertainty can justify a call.",
              "task": {"instruction": rows[0]["instruction"], "constraints": rows[0]["constraints"]},
              "calls": []}
    # Deliberately omit method, final benchmark success, and model identity.
    for start in starts:
        end = ends.get(start["call_id"])
        bundle["calls"].append({
            "call_id": start["call_id"], "command": start["command"],
            "visible_tool_ids": start["visible_tool_ids"], "before_revision": start["before_revision"],
            "information_available_before_call": start["information_available_before_call"],
            "result": end.get("result") if end else None,
            "after_revision": end.get("after_revision") if end else None,
            "label": "unknown", "category": "", "reason": "",
            "evidence_call_ids": [], "task_evidence": "", "conditions_unchanged": None,
        })
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Audit destination exists; refusing to overwrite annotations")
    atomic_json(destination, bundle)
    return bundle


def audit_summary(result, rows, audit=None):
    starts = {r["call_id"]: r for r in rows if r["event"] == "tool_start"}
    ends = {r["call_id"]: r for r in rows if r["event"] == "tool_end"}
    if (len(starts) != sum(r["event"] == "tool_start" for r in rows)
            or len(ends) != sum(r["event"] == "tool_end" for r in rows)
            or set(ends) - set(starts) or result["tool_calls"] != len(starts)):
        raise ValueError("Duplicate/mismatched tool invocation accounting")
    complete_trace = set(starts) == set(ends)
    labels = {i: "unknown" for i in starts}
    if audit is not None:
        if (audit.get("schema") != "hai-contextual-audit-v1" or audit.get("run_id") != result["run_id"]
                or audit.get("trace_sha256") != result["trace_sha256"]):
            raise ValueError("Audit is not bound to this run/trace")
        calls = audit.get("calls")
        if not isinstance(calls, list) or len(calls) != len(starts) or {r.get("call_id") for r in calls} != set(starts):
            raise ValueError("Audit must include each attempted tool call exactly once")
        if any(r.get("label") != "unknown" for r in calls) and not str(audit.get("reviewer", "")).strip():
            raise ValueError("Labeled audit requires an identified reviewer")
        for row in calls:
            call_id = row["call_id"]
            label = row.get("label")
            if label not in {"redundant", "nonredundant", "unknown"}:
                raise ValueError("Invalid audit label")
            if label != "unknown" and (call_id not in ends or not str(row.get("reason", "")).strip()):
                raise ValueError("Label needs a completed call and contextual rationale")
            if label == "redundant":
                sources = row.get("evidence_call_ids")
                task_evidence = row.get("task_evidence", "")
                supported_by_task = (row.get("category") == "irrelevant_to_goal"
                    and isinstance(task_evidence, str) and len(task_evidence.strip()) >= 5
                    and task_evidence in (rows[0]["instruction"] + "\n" + "\n".join(rows[0]["constraints"])))
                if (row.get("category") not in REDUNDANT_CATEGORIES or row.get("conditions_unchanged") is not True
                        or not isinstance(sources, list) or not (sources or supported_by_task)
                        or not all(type(i) is int and i < call_id and i in starts[call_id]["visible_tool_ids"] for i in sources)):
                    raise ValueError("Redundancy requires a supported category, unchanged relevant premises, and prior visible evidence")
            # Evidence fields must be those in the immutable trace, not edited to justify a label.
            end = ends.get(call_id)
            for key, expected in {"command": starts[call_id]["command"],
                                  "visible_tool_ids": starts[call_id]["visible_tool_ids"],
                                  "before_revision": starts[call_id]["before_revision"],
                                  "information_available_before_call": starts[call_id]["information_available_before_call"],
                                  "result": end.get("result") if end else None,
                                  "after_revision": end.get("after_revision") if end else None}.items():
                if row.get(key) != expected:
                    raise ValueError("Audit evidence was modified")
            labels[call_id] = label
    n = len(starts)
    redundant = sum(v == "redundant" for v in labels.values())
    unknown = sum(v == "unknown" for v in labels.values())
    return {"definition": "contextually_avoidable_tool_invocations_v1", "tool_calls": n,
            "redundant_calls": redundant, "unknown_calls": unknown,
            "audit_coverage": (n - unknown) / n if n else None,
            "tool_redundancy_rate": redundant / n if n and not unknown and complete_trace else None,
            "redundancy_lower_bound": redundant / n if n else None,
            "redundancy_upper_bound": (redundant + unknown) / n if n else None,
            "trace_complete": complete_trace,
            "status": "no_tool_calls" if not n else "audited" if not unknown and complete_trace else "requires_contextual_audit"}


def attach_evaluation(directory, report_path):
    """Explicit offline import only, not an official evaluator or model self-judgment."""
    directory, report_path = Path(directory), Path(report_path)
    result, _ = load_run(directory)
    if result.get("submitted") is not True or not isinstance(result.get("artifact"), dict):
        raise ValueError("Evaluation requires an explicitly submitted, immutable candidate artifact")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    expected = result["artifact"]["sha256"] if result.get("artifact") else None
    if (report.get("schema") != "hai-external-evaluation-v1"
            or report.get("run_id") != result["run_id"] or report.get("task_id") != result["task_id"]
            or report.get("artifact_sha256") != expected
            or type(report.get("success")) is not bool or not isinstance(report.get("evaluator"), str)
            or not report["evaluator"].strip() or report.get("independent") is not True):
        raise ValueError("Evaluation must identify this task/run/artifact and an independent boolean result")
    # Keep the original external test report alongside its digest for auditability.
    source = report.get("source_report")
    if not isinstance(source, str):
        raise ValueError("source_report path to actual external test result required")
    source_path = (report_path.parent / source).resolve()
    source_bytes = source_path.read_bytes()
    if report.get("source_sha256") != hashlib.sha256(source_bytes).hexdigest():
        raise ValueError("External source report checksum mismatch")
    parsed = source_success(json.loads(source_bytes), result["task_id"], report.get("source_format"))
    if parsed is not report["success"]:
        raise ValueError("Normalized success contradicts the external source report")
    destination = directory / "evaluation.json"
    if destination.exists():
        raise ValueError("Evaluation already attached; do not silently overwrite")
    # Keep a portable exact-byte copy, not a reference that breaks when the run moves.
    source_copy = directory / "evaluation-source.json"
    with source_copy.open("xb") as stream:
        stream.write(source_bytes)
    attached = report | {"source_report": source_copy.name, "normalized_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest()}
    atomic_json(destination, attached)
    return attached


def summarize_run(directory, audit_path=None):
    directory = Path(directory)
    result, rows = load_run(directory)
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8")) if audit_path else None
    redundancy = audit_summary(result, rows, audit)
    api = [r for r in rows if r["event"] == "api_end"]
    api_starts = sum(r["event"] == "api_start" for r in rows)
    usage = [r["usage"] for r in api if isinstance(r.get("usage"), dict)]
    turns = sum(r["event"] == "model_response" for r in rows)
    if turns != result["interaction_rounds"]:
        raise ValueError("Turn count mismatch")
    evaluation_path = directory / "evaluation.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8")) if evaluation_path.exists() else None
    success = None
    if evaluation:
        if result.get("submitted") is not True or not isinstance(result.get("artifact"), dict):
            raise ValueError("Non-submitted run cannot carry an evaluation result")
        expected = result["artifact"]["sha256"] if result.get("artifact") else None
        if (evaluation.get("run_id") != result["run_id"] or evaluation.get("artifact_sha256") != expected
                or evaluation.get("task_id") != result["task_id"] or type(evaluation.get("success")) is not bool
                or evaluation.get("independent") is not True):
            raise ValueError("Evaluation/run mismatch")
        source_bytes = (directory / evaluation["source_report"]).read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != evaluation["source_sha256"]:
            raise ValueError("External evaluation source has changed")
        success = source_success(json.loads(source_bytes), result["task_id"], evaluation.get("source_format"))
        if success is not evaluation["success"]:
            raise ValueError("Normalized success contradicts the external source report")
    requests = [r for r in rows if r["event"] == "request_context"]
    decisions = [r for r in rows if r["event"] == "decision" and r.get("decision", {}).get("action") == "run"]
    strategy_rows = [r for r in rows if r["event"] == "strategy_observed"]
    subgoal_rows = [r for r in rows if r["event"] == "subgoal_observed"]
    repeat_rows = [r for r in rows if r["event"] == "repeat_decision"]
    interventions = [r for r in rows if r["event"] == "memory_intervention"]
    reconsiderations = [r for r in rows if r["event"] == "memory_reconsideration"]
    followups = [r for r in rows if r["event"] == "memory_followup_outcome"]
    strategy_labels = [r.get("strategy", {}).get("strategy") for r in strategy_rows]
    subgoal_labels = [r.get("subgoal", {}).get("subgoal") for r in subgoal_rows]
    def switches(labels):
        values = [v for v in labels if isinstance(v, str) and v]
        return sum(a != b for a, b in zip(values, values[1:]))
    mechanism = {
        "enabled": result["method"] == "hai",
        "run_decisions": len(decisions),
        "model_declared_strategy_actions": sum(bool(r["decision"].get("strategy", "").strip()) for r in decisions),
        "inferred_strategy_actions": sum(r["event"] == "strategy_inferred" for r in rows),
        "unique_strategies": len({v for v in strategy_labels if isinstance(v, str) and v}),
        "strategy_switches": switches(strategy_labels),
        "model_declared_subgoal_actions": sum(bool(r["decision"].get("subgoal", "").strip()) for r in decisions),
        "inferred_subgoal_actions": sum(r["event"] == "subgoal_inferred" for r in rows),
        "unique_subgoals": len({v for v in subgoal_labels if isinstance(v, str) and v}),
        "subgoal_switches": switches(subgoal_labels),
        "model_memory_admissions": sum(r["event"] == "memory_admission" for r in rows),
        "memory_rejections": sum(r["event"] == "memory_rejected" for r in rows),
        "automatic_memory_updates": sum(r["event"] == "automatic_memory" for r in rows),
        "memory_recall_exposures": sum(len(r.get("selected_memory_ids", [])) for r in requests),
        "requests_with_recalled_memory": sum(bool(r.get("selected_memory_ids")) for r in requests),
        "repetition_observations": sum(r["event"] == "repetition_observed" for r in rows),
        "repeat_decisions": len(repeat_rows),
        "repeat_executed": sum(r.get("executed") is True for r in repeat_rows),
        "repeat_blocked": sum(r.get("executed") is False for r in repeat_rows),
        "unverified_scope_soft_retries": sum(r.get("permission_mode") == "unverified_scope_soft_retry" for r in repeat_rows),
        "explained_retries": sum(r.get("permission_mode") == "bounded_explained_retry" for r in repeat_rows),
        "memory_interventions": len(interventions),
        "memory_reconsiderations": len(reconsiderations),
        "memory_action_changed": sum(r.get("changed_action") is True for r in reconsiderations),
        "memory_action_unchanged": sum(r.get("changed_action") is False for r in reconsiderations),
        "memory_direction_changed": sum(r.get("changed_direction") is True for r in reconsiderations),
        "memory_direction_unchanged": sum(r.get("changed_direction") is False for r in reconsiderations),
        "memory_exact_action_changed": sum(r.get("changed_action") is True for r in reconsiderations),
        "memory_override_reasons": sum(r["event"] == "memory_override_reason" for r in rows),
        "memory_override_reasons_exhausted": sum(
            r["event"] == "memory_override_reason_exhausted" for r in rows),
        "memory_overrides_exhausted": sum(r["event"] == "memory_override_exhausted" for r in rows),
        "memory_use_self_reports": sum(len(r.get("memory_ids", [])) for r in rows
                                       if r["event"] == "memory_use_self_report"),
        "memory_followup_actions": len(followups),
        "memory_followup_runs": sum(r.get("action_kind") == "run" for r in followups),
        "memory_followup_succeeded": sum(r.get("action_kind") == "run" and
                                         r.get("succeeded") is True for r in followups),
        "memory_followup_workspace_changed": sum(r.get("action_kind") == "run" and
                                                  r.get("workspace_changed") is True for r in followups),
        "direction_stalls": sum(r["event"] == "automatic_memory" and
                                str(r.get("conclusion", "")).startswith("The direction '")
                                for r in rows),
        "memory_intervention_followup_coverage": (
            len(followups) / len(reconsiderations) if reconsiderations else None),
        "memory_behavior_chain_is_association_not_causation": True,
    }
    return {"run_id": result["run_id"], "task_id": result["task_id"], "method": result["method"],
            "submitted": result["submitted"], "stop_reason": result["stop_reason"],
            "success": success, "interaction_rounds": turns,
            "tool_feedback_rounds": sum(r["event"] == "tool_end" for r in rows),
            "api_requests": api_starts,
            "api_usage_coverage": len(usage) / api_starts if api_starts else None,
            "reported_prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
            "reported_completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
            "format_errors": sum(r["event"] == "format_error" for r in rows),
            "wall_seconds": result["wall_seconds"], "mechanism_utilization": mechanism,
            **redundancy}


def summarize_manifest(manifest_path):
    """Frozen task list with explicit run mapping; missing tasks never disappear."""
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    ids, methods = manifest["task_ids"], manifest["methods"]
    if not ids or len(ids) != len(set(ids)) or not methods:
        raise ValueError("Nonempty unique frozen task IDs/methods required")
    report = {"schema": "hai-comparison-v1", "manifest_sha256": digest(manifest), "task_ids": ids, "methods": {}}
    shared_configs = []
    task_identities = {}
    for name, entries in methods.items():
        if not isinstance(entries, dict) or set(entries) - set(ids):
            raise ValueError("Run mapping contains tasks outside frozen list")
        summaries, seen_runs = {}, set()
        for task_id, entry in entries.items():
            if not (path.parent / entry["run"] / "result.json").is_file():
                # A planned but unfinished/missing run is not a zero-round task.
                continue
            audit = path.parent / entry["audit"] if entry.get("audit") else None
            if audit is not None and not audit.is_file():
                audit = None
            summary = summarize_run(path.parent / entry["run"], audit)
            _, rows = load_run(path.parent / entry["run"])
            protocol = rows[0]["protocol"]
            common_config = {k: v for k, v in protocol["config"].items() if k != "method"}
            shared_configs.append({"config": common_config, "model": protocol["model"], "endpoint": protocol["endpoint"],
                                   "protocol_version": protocol["version"], "source_sha256": protocol.get("source_sha256")})
            identity = {k: rows[0][k] for k in ("instruction", "constraints", "base_commit", "environment_revision", "environment_keys")}
            if task_id in task_identities and task_identities[task_id] != identity:
                raise ValueError("Paired task instructions/base/environment declarations differ")
            task_identities[task_id] = identity
            if summary["task_id"] != task_id or summary["method"] != name or summary["run_id"] in seen_runs:
                raise ValueError("Mismatched/duplicate task run")
            seen_runs.add(summary["run_id"])
            summaries[task_id] = summary
        values = list(summaries.values())
        evaluated = [r for r in values if r["success"] is not None]
        successful = [r for r in evaluated if r["success"]]
        whole = len(values) == len(ids)
        full_eval = len(evaluated) == len(ids)
        calls = sum(r["tool_calls"] for r in values)
        all_audited = whole and all(r["status"] in {"audited", "no_tool_calls"} for r in values)
        rates = [r["tool_redundancy_rate"] for r in values if r["tool_redundancy_rate"] is not None]
        report["methods"][name] = {
            "planned_tasks": len(ids), "completed_runs": len(values), "evaluated_tasks": len(evaluated),
            "successes": len(successful), "success_rate": len(successful) / len(ids) if full_eval else None,
            "success_rate_lower_bound": len(successful) / len(ids),
            "success_rate_upper_bound": (len(successful) + len(ids) - len(evaluated)) / len(ids),
            "average_interaction_rounds": mean(r["interaction_rounds"] for r in values) if whole else None,
            "completed_run_average_rounds": mean(r["interaction_rounds"] for r in values) if values else None,
            "successful_only_average_rounds": mean(r["interaction_rounds"] for r in successful) if full_eval and successful else None,
            "tool_redundancy_rate": sum(r["redundant_calls"] for r in values) / calls if all_audited and calls else None,
            "macro_task_redundancy_rate": mean(rates) if all_audited and rates else None,
            "tool_calls": calls, "unknown_calls": sum(r["unknown_calls"] for r in values),
            "zero_tool_tasks": sum(r["tool_calls"] == 0 for r in values),
            "missing_task_ids": [i for i in ids if i not in summaries], "tasks": summaries}
    report["common_model_and_budget_match"] = all(c == shared_configs[0] for c in shared_configs) if shared_configs else None
    if report["common_model_and_budget_match"] is False:
        raise ValueError("Comparison refused: methods do not share model/provider/budget settings")
    if "hai" in report["methods"] and "raw" in report["methods"]:
        hai, raw = report["methods"]["hai"], report["methods"]["raw"]
        def relative(a, b, decrease=False):
            return ((b - a) if decrease else (a - b)) / b if a is not None and b is not None and b != 0 else None
        paired = [i for i in ids if i in hai["tasks"] and i in raw["tasks"]
                  and hai["tasks"][i]["success"] is not None and raw["tasks"][i]["success"] is not None]
        both = [i for i in paired if hai["tasks"][i]["success"] and raw["tasks"][i]["success"]]
        report["paired_comparison"] = {
            "evaluated_pairs": len(paired), "hai_only_success": sum(hai["tasks"][i]["success"] and not raw["tasks"][i]["success"] for i in paired),
            "raw_only_success": sum(raw["tasks"][i]["success"] and not hai["tasks"][i]["success"] for i in paired),
            "both_success": len(both),
            "success_difference_percentage_points": 100 * (hai["success_rate"] - raw["success_rate"]) if hai["success_rate"] is not None and raw["success_rate"] is not None else None,
            "success_relative_improvement": relative(hai["success_rate"], raw["success_rate"]),
            "rounds_relative_reduction": relative(hai["average_interaction_rounds"], raw["average_interaction_rounds"], True),
            "redundancy_relative_reduction": relative(hai["tool_redundancy_rate"], raw["tool_redundancy_rate"], True),
            "both_success_mean_rounds": {method: mean(report["methods"][method]["tasks"][i]["interaction_rounds"] for i in both) if both else None for method in ("hai", "raw")},
        }
    return report
