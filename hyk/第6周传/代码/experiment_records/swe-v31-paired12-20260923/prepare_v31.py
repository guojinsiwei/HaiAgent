"""Freeze a deterministic 12-task view of the existing prepared SWE cohort."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

CODE = Path("/mnt/lizh639/BestFGS-blocking-memory-v12")
SOURCE = Path("/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen")
ROOT = Path("/mnt/lizh639/bestfgs-runs/swe-v31-paired12-20260923")
SEED = "swe-v31-paired12-20260923"
COUNT = 12

sys.path[:0] = [str(CODE), str(CODE / "src")]
from benchmark_runtime import atomic_write_json, canonical_sha256
from swe_batch import load_plan


def rank(identity: str) -> tuple[str, str]:
    return hashlib.sha256((SEED + "\0" + identity).encode()).hexdigest(), identity


def main() -> None:
    source = load_plan(SOURCE / "task-plan.json")
    selected = sorted(source["tasks"], key=lambda task: rank(task["instance_id"]))[:COUNT]
    plan = {
        key: value
        for key, value in source.items()
        if key not in {"tasks", "count", "plan_sha256", "purpose"}
    }
    plan.update(
        count=COUNT,
        tasks=selected,
        purpose="exploratory_paired_harness_benefit_lower_model_tier",
        source_plan_sha256=source["plan_sha256"],
        subset_seed=SEED,
        subset_rule="sort by SHA256(seed + NUL + instance_id), take first 12; no outcome filtering",
    )
    plan["plan_sha256"] = canonical_sha256(plan)
    ROOT.mkdir(parents=True, exist_ok=False)
    atomic_write_json(ROOT / "task-plan.json", plan)
    atomic_write_json(
        ROOT / "preparation.json",
        {
            "state": "prepared_no_model_calls",
            "paid_model_requests": 0,
            "source_prepared_root": str(SOURCE),
            "task_count": COUNT,
            "method_runs": COUNT * 2,
            "selection_ids": [task["instance_id"] for task in selected],
            "plan_sha256": plan["plan_sha256"],
        },
    )
    print(json.dumps({"prepared": True, "ids": [task["instance_id"] for task in selected],
                      "plan_sha256": plan["plan_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
