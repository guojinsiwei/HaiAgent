"""Reconcile existing experiment metrics with official labels; no model/Docker calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark_metrics import (
    print_official_interaction_summary,
    summarize_official_interactions,
    summarize_research_metrics,
    swe_official_outcomes,
    terminal_official_outcomes,
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--swe-run-id")
    parser.add_argument("--swe-results-dir", type=Path,
                        default=Path(__file__).parent / "benchmark_results" / "swebench")
    parser.add_argument("--terminal-job-dir", type=Path)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent / "benchmark_results" / "reconciled")
    args = parser.parse_args(argv)
    if not args.swe_run_id and args.terminal_job_dir is None:
        parser.error("specify --swe-run-id and/or --terminal-job-dir")
    reports = []
    if args.swe_run_id:
        if Path(args.swe_run_id).name != args.swe_run_id or any(c in args.swe_run_id for c in "/\\"):
            parser.error("swe-run-id must be a run name, not a path")
        base = args.swe_results_dir
        report_path = base / f"official-report-{args.swe_run_id}.json"
        agents_path = base / f"agent-results-{args.swe_run_id}.json"
        official, rows = read_json(report_path), read_json(agents_path)
        summary = summarize_official_interactions(
            rows, swe_official_outcomes(official), id_key="instance_id",
            rounds_key="agent_interaction_rounds", success_key="agent_succeeded",
            selected_count=official["total_instances"],
        )
        summary["research_metrics"] = summarize_research_metrics(rows)
        summary["source_files"] = [str(report_path.resolve()), str(agents_path.resolve())]
        reports.append((args.swe_run_id, summary))
    if args.terminal_job_dir is not None:
        base = args.terminal_job_dir
        official = read_json(base / "result.json")
        rows = []
        for path in sorted(base.glob("*/agent/retrac_result.json")):
            row = read_json(path)
            row["trial_name"] = path.parent.parent.name
            rows.append(row)
        summary = summarize_official_interactions(
            rows, terminal_official_outcomes(official), id_key="trial_name",
            selected_count=official["n_total_trials"],
        )
        summary["research_metrics"] = summarize_research_metrics(rows)
        summary["source_job_directory"] = str(base.resolve())
        reports.append((base.name, summary))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, summary in reports:
        target = args.output_dir / f"official-interaction-summary-{name}.json"
        target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(name)
        print_official_interaction_summary(summary)
        print(f"校正报告：{target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
