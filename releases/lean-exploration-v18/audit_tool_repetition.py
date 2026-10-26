"""Offline mechanical-repeat reports and trace-bound contextual audit packets.

Never runs task code, calls a model, grades a patch, or guesses semantic labels.
All outputs require fresh filenames. Old traces are read, never rewritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from benchmark_runtime import canonical_sha256
from bestfgs.experiment_metrics import METRIC_REPORT_VERSION, summarize_trace

AUDIT_VERSION = "contextual-repeat-audit-v2"
LABELS = {"avoidable_repeat", "necessary_reverification", "other_nonredundant", "uncertain"}
RUBRIC = {
    "avoidable_repeat": "Earlier available evidence already answers the same question under still-applicable conditions; no concrete progress, new information or justified safety/verification need. Cite earlier call IDs and contextual evidence.",
    "necessary_reverification": "A justified recheck (e.g. changed relevant implementation, final artifact integrity or external-state uncertainty). Phase alone is insufficient; cite context.",
    "other_nonredundant": "Not an avoidable repetition: new relevant evidence or task progress. Failure alone does not make a call redundant.",
    "uncertain": "Insufficient context or unresolved necessity/applicability. Never silently count this as nonredundant.",
    "instructions": "Review full execution context, not only hashes, method name, success outcome or mechanical_repeat flag. A differently worded command can still be avoidable. No automatic labels. Apply the same rubric to both methods.",
}
ANNOTATIONS = {"label", "reviewer", "rationale", "evidence_refs", "earlier_call_ids"}


def trace_calls(path):
    metrics = summarize_trace(path)
    if not metrics["trace_complete"]:
        raise ValueError("Audit requires a complete trace; incomplete work is not zero repetition")
    events = [json.loads(line) for line in Path(path).read_bytes().splitlines()]
    starts, ends = {}, {}
    for event in events:
        if event.get("event") not in {"tool_start", "tool_end"}:
            continue
        identity = event.get("call_id")
        if type(identity) is not int or identity <= 0:
            raise ValueError("Invalid call ID")
        target = starts if event["event"] == "tool_start" else ends
        if identity in target:
            raise ValueError("Duplicate trace call ID")
        if event["event"] == "tool_end" and identity not in starts:
            raise ValueError("Result appears before its command")
        target[identity] = event
    if set(starts) != set(ends):
        raise ValueError("Unpaired trace calls")
    rows = []
    for identity in sorted(starts):
        start, end = starts[identity], ends[identity]
        mechanical_repeat = end.get("mechanical_repeat", end.get("redundant"))
        if type(mechanical_repeat) is not bool:
            raise ValueError("Missing mechanical-repeat observation")
        automatic = end.get("redundancy", {})
        rows.append({"call_id": identity, "round_id": start.get("round_id"),
                     "phase": start.get("phase"), "command_sha256": start.get("command_sha256"),
                     "before_sha256": start.get("before_sha256"), "after_sha256": end.get("after_sha256"),
                     "observation_sha256": end.get("observation_sha256"),
                     "mechanical_repeat": mechanical_repeat,
                     "automatic_classification": automatic.get("classification"),
                     "automatic_reason": automatic.get("reason"),
                     "automatic_earlier_call_id": automatic.get("earlier_call_id"),
                     "dependency_evidence": end.get("dependency_evidence")})
    return metrics, rows


def prepare_audit(trace, *, sample_size=30, seed=20260921):
    if type(sample_size) is not int or sample_size <= 0 or type(seed) is not int:
        raise ValueError("sample_size must be positive and seed integer")
    metrics, calls = trace_calls(trace)
    size = min(sample_size, len(calls))
    # Sample all completed calls, not just detector-positive repeats. Otherwise
    # missed semantic repeats could never enter the contextual audit.
    selected = sorted(random.Random(seed).sample(calls, size), key=lambda row: row["call_id"])
    protocol = {"audit_version": AUDIT_VERSION, "metric_report_version": METRIC_REPORT_VERSION,
                "trace_sha256": metrics["trace_sha256"], "population_size": len(calls),
                "requested_sample_size": sample_size, "seed": seed,
                "sampling": "uniform_without_replacement_over_all_completed_calls",
                "selected_call_ids": [row["call_id"] for row in selected], "rubric": dict(RUBRIC)}
    return {"protocol": protocol, "protocol_sha256": canonical_sha256(protocol),
            "context_warning": "Trace contains hashes, not full command/output context. Use original execution logs to justify each label. No label can be inferred from this packet alone.",
            "items": [{**row, "label": None, "reviewer": "", "rationale": "",
                       "evidence_refs": [], "earlier_call_ids": []} for row in selected]}


def summarize_audit(trace, packet):
    protocol = packet.get("protocol", {})
    if protocol.get("audit_version") != AUDIT_VERSION:
        raise ValueError("Unknown audit protocol")
    expected = prepare_audit(trace, sample_size=protocol.get("requested_sample_size"), seed=protocol.get("seed"))
    if protocol != expected["protocol"] or packet.get("protocol_sha256") != expected["protocol_sha256"]:
        raise ValueError("Audit does not match the original trace, fixed sample or rubric")
    items = packet.get("items")
    if not isinstance(items, list) or len(items) != len(expected["items"]):
        raise ValueError("Do not delete unreviewed items from the sample")
    _, calls = trace_calls(trace)
    all_ids = {row["call_id"] for row in calls}
    counts = Counter()
    mechanical_counts = Counter()
    for row, frozen in zip(items, expected["items"]):
        if not isinstance(row, dict) or {k: v for k, v in row.items() if k not in ANNOTATIONS} != {
            k: v for k, v in frozen.items() if k not in ANNOTATIONS
        }:
            raise ValueError("Audit call identity or measurements were changed")
        label = row.get("label")
        if label is None:
            counts["unreviewed"] += 1
            continue
        if not isinstance(label, str) or label not in LABELS:
            raise ValueError("Unknown contextual audit label")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("reviewer", "rationale")):
            raise ValueError("Reviewed labels require a reviewer and rationale")
        refs = row.get("evidence_refs")
        if not isinstance(refs, list) or not all(isinstance(v, str) and v.strip() for v in refs):
            raise ValueError("Evidence references must be a text list")
        if label != "uncertain" and not refs:
            raise ValueError("Decisive labels require contextual evidence references")
        earlier = row.get("earlier_call_ids")
        if (not isinstance(earlier, list) or any(type(v) is not int or v not in all_ids or v >= row["call_id"] for v in earlier)
                or len(set(earlier)) != len(earlier)):
            raise ValueError("Earlier references must identify distinct preceding calls")
        if label == "avoidable_repeat" and not earlier:
            raise ValueError("Avoidable repetition must cite an earlier call")
        counts[label] += 1
        if row["mechanical_repeat"]:
            mechanical_counts[label] += 1
    n = len(items)
    unresolved = counts["uncertain"] + counts["unreviewed"]
    return {"audit_version": AUDIT_VERSION, "protocol_sha256": expected["protocol_sha256"],
            "trace_sha256": protocol["trace_sha256"], "population_size": protocol["population_size"],
            "sample_size": n, "reviewed": n - counts["unreviewed"],
            "counts": {key: counts[key] for key in sorted(LABELS | {"unreviewed"})},
            "mechanical_repeat_label_counts": dict(mechanical_counts),
            "avoidable_repeat_rate_in_sample": counts["avoidable_repeat"] / n if n and not unresolved else None,
            "sample_rate_bounds_due_to_unknowns": [counts["avoidable_repeat"] / n,
                (counts["avoidable_repeat"] + unresolved) / n] if n else None,
            "whole_trace_avoidable_repeat_rate": counts["avoidable_repeat"] / n
                if n and n == protocol["population_size"] and not unresolved else None,
            "bounds_are_confidence_intervals": False, "causal_tool_calls_saved": None,
            "interpretation": "Descriptive contextual labels, not counterfactual proof. Unknowns remain in the denominator. A partial sample is not a full-run rate, and these bounds do not measure sampling uncertainty."}


def write_new(path, data):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("report", "prepare", "summarize"))
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260921)
    args = parser.parse_args(argv)
    try:
        if args.mode == "report":
            old = summarize_trace(args.trace)
            # Deliberately omit deprecated names from this user-facing view.
            keys = ("metric_version", "metric_report_version", "interaction_rounds", "tool_calls",
                    "trace_complete", "trace_sha256", "mechanical_repeat_calls", "mechanical_repeat_rate",
                    "mechanical_repeat_by_phase", "metric_interpretation", "redundancy_version",
                    "confirmed_reusable_calls", "confirmed_reusable_call_rate",
                    "confirmed_reusable_by_phase", "unclassified_tool_calls",
                    "classification_coverage", "unknown_call_rate",
                    "confirmed_reusable_rate_sensitivity_bounds", "confirmed_reusable_status")
            result = {key: old.get(key) for key in keys}
        elif args.mode == "prepare":
            result = prepare_audit(args.trace, sample_size=args.sample_size, seed=args.seed)
        else:
            if args.audit is None:
                raise ValueError("summarize requires --audit")
            result = summarize_audit(args.trace, json.loads(args.audit.read_text(encoding="utf-8")))
        write_new(args.output, result)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(f"Saved offline {args.mode}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
