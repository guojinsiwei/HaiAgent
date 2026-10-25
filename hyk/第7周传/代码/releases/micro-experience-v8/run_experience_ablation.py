"""Prepare/execute a bounded, fresh three-arm development ablation; never grade it."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from urllib.parse import urlsplit

import run_notebook as notebook
from benchmark_runtime import atomic_write_json, canonical_sha256, implementation_sha256
from bestfgs.experiment_metrics import METRIC_VERSION, summarize_trace

ROOT = Path(__file__).resolve().parent
MODES = ("off", "legacy", "conditioned")
MAX_TASKS = 10
PROTOCOL_VERSION = "experience-development-ablation-v1"
PUBLIC_ENV = ("OPENAI_MODEL", "DEEPSEEK_MODEL", "DASHSCOPE_MODEL", "OPENAI_API_BASE",
              "OPENAI_BASE_URL", "DEEPSEEK_API_BASE", "DASHSCOPE_API_BASE",
              "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
USAGE_FIELDS = ("model_calls", "api_requests", "api_responses", "prompt_tokens", "completion_tokens",
                "cached_prompt_tokens", "cache_miss_prompt_tokens", "cache_write_prompt_tokens",
                "usage_missing_responses", "usage_unreported_requests")


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_endpoint(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("API endpoint must be HTTPS without credentials, query or fragment")
    return value.rstrip("/")


@contextmanager
def no_git_refresh():
    # run_notebook validates Git status; avoid its optional index refresh changing
    # the very seed fingerprint that we are checking. This never changes Git config.
    previous = os.environ.get("GIT_OPTIONAL_LOCKS")
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("GIT_OPTIONAL_LOCKS", None)
        else:
            os.environ["GIT_OPTIONAL_LOCKS"] = previous


def runtime_fingerprint(python):
    """Read-only installed-metadata check, not a full container/OS fingerprint."""
    python = Path(python).absolute()
    if not python.is_file():
        raise ValueError(f"Python executable does not exist: {python}")
    prefix = python.parent.parent if python.parent.name.lower() in {"bin", "scripts"} else python.parent
    paths = set(prefix.glob("conda-meta/*.json"))
    sites = [prefix / "Lib/site-packages", *prefix.glob("lib/python*/site-packages")]
    for site in sites:
        for pattern in ("*.dist-info/METADATA", "*.egg-info/PKG-INFO", "*.pth"):
            paths.update(site.glob(pattern))
    records = [(path.relative_to(prefix).as_posix(), file_hash(path)) for path in sorted(paths) if path.is_file()]
    return {"path": str(python), "executable_sha256": file_hash(python),
            "installed_metadata_sha256": canonical_sha256(records), "metadata_files": len(records)}


def implementation_identity():
    # Keep this explicit even if benchmark_runtime's registry is later extended.
    return {"runner_and_agent_sha256": implementation_sha256(ROOT),
            "ablation_orchestrator_sha256": file_hash(Path(__file__))}


def common_arguments(args):
    result = ["--provider", "deepseek", "--model", args.model, "--base-url", safe_endpoint(args.base_url),
              "--api-key-env", "DEEPSEEK_API_KEY", "--temperature", str(args.temperature),
              "--reasoning-effort", args.reasoning_effort, "--solve-reasoning-effort", args.reasoning_effort,
              "--max-iterations", str(args.max_iterations), "--max-tool-calls", str(args.max_tool_calls),
              "--max-commands-per-action", str(args.max_commands_per_action),
              "--budget-multiplier", "1", "--no-adaptive-budget", "--success-judge-mode", "off",
              "--comparison-metrics", "--model-timeout", "90", "--model-max-wall-time", "600",
              "--model-request-attempts", "5", "--model-parse-attempts", "3",
              "--model-retry-interval", "2", "--model-max-retry-interval", "30"]
    if args.top_p is not None:
        result.extend(["--top-p", str(args.top_p)])
    return result


def build_plan(args):
    manifest = args.task_manifest.resolve()
    output = args.output_root.resolve()
    # Bound before expensive seed walks. Only run_notebook schema is accepted;
    # raw HF/SWE rows and a 100-task batch are not silently reinterpreted/subsampled.
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("tasks"), list):
        raise ValueError("Use a prepared run_notebook manifest: schema_version=1, benchmark, tasks[]")
    if not 1 <= len(data["tasks"]) <= MAX_TASKS:
        raise ValueError("Development ablation requires 1-10 explicitly selected tasks; supply a small manifest")
    if output.exists():
        raise ValueError("Output root already exists; use a NEW directory (no automatic retry/resume/overwrite)")
    if not args.model.strip() or args.model.startswith("sk-"):
        raise ValueError("Provide a public model identifier, never an API key")
    if any(value <= 0 for value in (args.max_iterations, args.max_tool_calls, args.max_commands_per_action)):
        raise ValueError("Budgets must be positive")
    if not math.isfinite(args.task_timeout) or args.task_timeout <= 0:
        raise ValueError("Task timeout must be finite and positive")
    if not math.isfinite(args.temperature) or not 0 <= args.temperature <= 2:
        raise ValueError("Temperature must be finite in [0, 2]")
    if args.top_p is not None and (not math.isfinite(args.top_p) or not 0 < args.top_p <= 1):
        raise ValueError("top-p must be finite in (0, 1]")
    with no_git_refresh():
        benchmark, tasks = notebook.load_tasks(manifest, output)
    public_env = {key: os.environ.get(key) for key in PUBLIC_ENV}
    for key, value in public_env.items():
        if value and ("BASE" in key):
            safe_endpoint(value)
    python = Path(args.python).absolute()
    runtimes = {str(python): runtime_fingerprint(python)}
    for task in tasks:
        raw = args.task_python or task.get("task_python")
        if not raw:
            raise ValueError("Specify --task-python or a prepared task_python on EVERY task; no implicit runtime")
        task_python = Path(raw)
        if not task_python.is_absolute():
            task_python = manifest.parent / task_python
        task_python = task_python.absolute()
        task["task_python"] = str(task_python)
        if str(task_python) not in runtimes:
            runtimes[str(task_python)] = runtime_fingerprint(task_python)
    common = common_arguments(args)
    # One randomly rotated Latin schedule balances order to within one task.
    # This seed controls scheduling ONLY, not the provider's stochastic generation.
    order = list(MODES)
    random.Random(args.schedule_seed).shuffle(order)
    schedule = [{"id": task["id"], "modes": order[i % 3:] + order[:i % 3]} for i, task in enumerate(tasks)]
    protocol = {"version": PROTOCOL_VERSION, "benchmark": benchmark, "purpose": "development_only",
                "manifest_sha256": file_hash(manifest), "expected_ids": [t["id"] for t in tasks],
                "tasks": tasks, "modes": list(MODES), "common_agent_args": common,
                "python": str(python), "runtime_fingerprints": runtimes, "task_timeout": args.task_timeout,
                "model_environment": public_env, "implementation": implementation_identity(),
                "metric_version": METRIC_VERSION, "schedule_seed": args.schedule_seed, "schedule": schedule,
                "attempts_per_task_arm": 1, "task_budget_multiplier": 1,
                "ordinary_history_retained_in_all_arms": True, "official_evaluation": False,
                "mode_semantics": {"off": "No experience retrieval/evaluation; shadow observations only; ordinary history/facts retained",
                                   "legacy": "Legacy experience use within the new shared delivery/runtime implementation",
                                   "conditioned": "Conditioned experience use within the same delivery/runtime implementation"}}
    return {"protocol": protocol, "protocol_sha256": canonical_sha256(protocol), "output_root": str(output),
            "task_manifest": str(manifest), "execution_requested": bool(args.execute),
            "notes": ["No automatic official evaluation or paid calls in the default plan mode.",
                      "Maximum 30 method runs; this is not the frozen 100-task experiment.",
                      "off does not erase conversation history or ordinary task facts.",
                      "Metadata/seed fingerprints do not freeze remote API weights, OS services or external state."]}


def jobs(plan):
    protocol = plan["protocol"]
    root = Path(plan["output_root"])
    tasks = {task["id"]: task for task in protocol["tasks"]}
    for entry in protocol["schedule"]:
        for mode in entry["modes"]:
            task = tasks[entry["id"]]
            output = root / "arms" / mode / task["id"]
            extra = [*protocol["common_agent_args"], "--experience-mode", mode]
            argv = ["--task-manifest", str(root / "manifests" / (task["id"] + ".json")),
                    "--output-root", str(output), "--python", protocol["python"],
                    "--task-python", task["task_python"], "--task-timeout", str(protocol["task_timeout"]),
                    "--method", "bestfgs", "--", *extra]
            yield {"id": task["id"], "mode": mode, "output_root": str(output), "argv": argv, "extra": extra}


def check_frozen_inputs(plan):
    protocol = plan["protocol"]
    if canonical_sha256(protocol) != plan["protocol_sha256"]:
        raise ValueError("Protocol hash mismatch")
    if implementation_identity() != protocol["implementation"]:
        raise ValueError("Implementation changed; stop, do not mix implementations")
    if file_hash(plan["task_manifest"]) != protocol["manifest_sha256"]:
        raise ValueError("Source task manifest changed")
    for task in protocol["tasks"]:
        if notebook.tree_digest(Path(task["workspace"])) != task["seed_sha256"]:
            raise ValueError(f"Prepared seed changed: {task['id']}")
    for path, expected in protocol["runtime_fingerprints"].items():
        if runtime_fingerprint(path) != expected:
            raise ValueError("Prepared Python/package metadata changed")


def execute_job(job, plan, environment):
    """Existing notebook launcher owns validation, child lifetime, trace and patch export."""
    directory = Path(job["output_root"]).parent
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (job["id"] + ".launcher.log")).open("x", encoding="utf-8") as log:
        return subprocess.run([plan["protocol"]["python"], str(ROOT / "run_notebook.py"), *job["argv"]],
                              cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False).returncode


def execute_plan(plan, executor=None):
    if not plan.get("execution_requested"):
        raise ValueError("Execution requires explicit --execute")
    check_frozen_inputs(plan)
    task_map = {task["id"]: task for task in plan["protocol"]["tasks"]}
    # Validate flags before creating any output or making requests. No legacy
    # termination flag is used: all arms retain production explicit submission.
    for job in jobs(plan):
        notebook.agent_arguments(task_map[job["id"]], Path(job["output_root"]) / "snapshots", job["extra"])
    environment = dict(os.environ)  # Never serialize secrets; one common credential snapshot for all arms.
    if not environment.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("DEEPSEEK_API_KEY is not set; enter it privately in the launch terminal")
    for key, value in plan["protocol"]["model_environment"].items():
        if environment.get(key) != value:
            raise ValueError("Public model/thread environment changed since planning")
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    root = Path(plan["output_root"])
    root.mkdir(parents=True, exist_ok=False)  # Atomic ownership; even an empty old directory is refused.
    atomic_write_json(root / "ablation-plan.json", plan)
    for task in task_map.values():
        atomic_write_json(root / "manifests" / (task["id"] + ".json"),
                          {"schema_version": 1, "benchmark": plan["protocol"]["benchmark"], "tasks": [task]})
    execute = executor or execute_job
    errors = False
    for job in jobs(plan):
        check_frozen_inputs(plan)  # Any drift stops ALL remaining arms, not just one.
        started = time.monotonic()
        record = {"id": job["id"], "mode": job["mode"], "status": "running", "attempt_count": 1,
                  "protocol_sha256": plan["protocol_sha256"]}
        record_path = root / "execution" / job["mode"] / (job["id"] + ".json")
        atomic_write_json(record_path, record)
        try:
            code = execute(job, plan, environment)
            record.update(status="finished" if code == 0 else "launcher_error", launcher_exit_code=code)
            errors = errors or code != 0
        except KeyboardInterrupt:
            record["status"] = "interrupted"
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            # Keep the task/arm and its partial artifacts; never retry invisibly.
            record.update(status="launcher_error", error_type=type(exc).__name__)
            errors = True
        finally:
            record["elapsed_seconds"] = time.monotonic() - started
            atomic_write_json(record_path, record)
        check_frozen_inputs(plan)
    atomic_write_json(root / "ablation-summary.json", summarize(root))
    return 2 if errors else 0


def read_optional(path):
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def valid_metrics(metrics):
    counts = [metrics.get(key) for key in ("interaction_rounds", "tool_calls", "redundant_tool_calls")]
    return (metrics.get("metric_version") == METRIC_VERSION and metrics.get("trace_complete") is True
            and all(type(v) is int and v >= 0 for v in counts) and counts[2] <= counts[1])


def collect_row(root, job):
    output = Path(job["output_root"])
    row = {"id": job["id"], "mode": job["mode"], "status": "not_started", "attempt_count": 0,
           "official_resolved": None, "comparison_metrics": None, "model_usage": None, "experience_report": None,
           "elapsed_seconds": None, "audit_errors": []}
    try:
        record = read_optional(root / "execution" / job["mode"] / (job["id"] + ".json"))
        row.update(attempt_count=record.get("attempt_count", 0), elapsed_seconds=record.get("elapsed_seconds"))
    except (OSError, ValueError, TypeError):
        record = {}
        row["audit_errors"].append("invalid execution record")
    try:
        if not output.resolve().is_relative_to(root.resolve()):
            raise ValueError("Task output escapes ablation root")
        state = read_optional(output / job["id"] / "status.json")
        row["status"] = state.get("status", record.get("status", "not_started"))
        attempt = state.get("attempt")
        if not attempt:
            # Recover only one unambiguous attempt from this fresh, single-attempt
            # task/arm. Never silently choose the latest among repeated attempts.
            candidates = list((output / job["id"]).glob("attempt-*"))
            if not candidates:
                if row["audit_errors"]:
                    row["status"] = "artifact_error"
                return row
            if len(candidates) != 1:
                raise ValueError("Multiple attempts violate the one-attempt protocol")
            attempt = candidates[0]
            row["status"] = "partial_artifacts"
            row["audit_errors"].append("missing status/attempt pointer; unique partial attempt retained")
        attempt = Path(attempt).resolve()
        if not attempt.is_relative_to(output.resolve()) or attempt == output.resolve():
            raise ValueError("Attempt path escapes this task/arm")
        result_path = attempt / "agent-result.json"
        try:
            result = read_optional(result_path)
            if state.get("result_sha256") and file_hash(result_path) != state["result_sha256"]:
                raise ValueError("agent-result checksum mismatch")
        except (OSError, ValueError, TypeError):
            result = {}
            row["audit_errors"].append("invalid agent-result/checksum; independent trace may still be readable")
            row["status"] = "artifact_error"
        row.update(delivery=result.get("delivery"), submitted=result.get("submitted", False),
                   local_validation_passed=result.get("local_validation_passed", False),
                   stop_reason=result.get("stop_reason"), model_usage=result.get("model_usage"),
                   experience_report=result.get("experience_report"),
                   comparison_metrics=result.get("comparison_metrics"))
        if row["experience_report"] is None:
            for path in (attempt / "experience_report.json", attempt / "snapshots/experience_report.json"):
                if path.is_file():
                    row["experience_report"] = read_optional(path)
                    break
        trace = attempt / "snapshots/cli-metrics.jsonl"
        if trace.is_file():
            replayed = summarize_trace(trace)
            previous = row["comparison_metrics"]
            if previous and any(previous.get(k) != replayed.get(k) for k in
                                ("interaction_rounds", "tool_calls", "redundant_tool_calls", "trace_complete")):
                row["audit_errors"].append("result/trace metric mismatch; using original recorder trace")
            row["comparison_metrics"] = replayed
        # A model's local success or submitted flag is NEVER official grading.
        report = row["experience_report"]
        if isinstance(report, dict) and report.get("mode") not in (None, job["mode"]):
            raise ValueError("Experience report mode does not match assigned arm")
        if "invalid execution record" in row["audit_errors"]:
            row["status"] = "artifact_error"
    except (OSError, ValueError, TypeError, KeyError) as exc:
        row["audit_errors"].append(type(exc).__name__ + ": invalid/incomplete artifacts")
        row["status"] = "artifact_error"
        row["comparison_metrics"] = None
    return row


def aggregate(rows):
    n = len(rows)
    available = [row for row in rows if isinstance(row.get("comparison_metrics"), dict) and valid_metrics(row["comparison_metrics"])]
    complete = len(available) == n
    calls = sum(row["comparison_metrics"]["tool_calls"] for row in available)
    repeats = sum(row["comparison_metrics"]["redundant_tool_calls"] for row in available)
    rounds = sum(row["comparison_metrics"]["interaction_rounds"] for row in available)
    totals = {}
    for key in USAGE_FIELDS:
        values = [(row["model_usage"] if isinstance(row.get("model_usage"), dict) else {}).get(key) for row in rows]
        observed = [v for v in values if type(v) in (int, float) and math.isfinite(v) and v >= 0]
        totals[key] = {"recorded_total": sum(observed) if observed else None, "tasks_recorded": len(observed),
                       "complete": len(observed) == n}
    by_phase = {}
    if complete and all(isinstance(row["comparison_metrics"].get("redundancy_by_phase"), dict) for row in rows):
        phases = {phase for row in rows for phase in row["comparison_metrics"]["redundancy_by_phase"]}
        for phase in sorted(phases):
            counts = [row["comparison_metrics"]["redundancy_by_phase"].get(phase, {}) for row in rows]
            if not all(isinstance(count, dict) and all(type(count.get(key, 0)) is int and count.get(key, 0) >= 0
                       for key in ("tool_calls", "redundant_tool_calls")) for count in counts):
                by_phase[phase] = {"tool_calls": None, "redundant_tool_calls": None, "rate": None}
                continue
            n_calls = sum(count.get("tool_calls", 0) for count in counts)
            n_repeat = sum(count.get("redundant_tool_calls", 0) for count in counts)
            by_phase[phase] = {"tool_calls": n_calls, "redundant_tool_calls": n_repeat,
                               "rate": n_repeat / n_calls if n_calls else None}
    return {"planned_N": n, "statuses": dict(Counter(row["status"] for row in rows)),
            "official_resolved": None, "known_resolved_count": 0, "official_unknown": n, "official_success_rate": None,
            "official_success_rate_bounds": [0, 1], "complete_metric_tasks": len(available),
            "missing_or_incomplete_metric_ids": [row["id"] for row in rows if row not in available],
            "mean_interaction_rounds": rounds / n if complete else None,
            "tool_calls": calls if complete else None, "redundant_tool_calls": repeats if complete else None,
            "tool_call_redundancy_rate_micro": repeats / calls if complete and calls else None,
            "recorded_complete_trace_subtotal": {"tool_calls": calls, "redundant_tool_calls": repeats, "interaction_rounds": rounds},
            "redundancy_by_phase": by_phase,
            "api_reported_models": sorted({model for row in rows if isinstance(row.get("model_usage"), dict)
                                           for model in (row["model_usage"].get("response_models") or []) if isinstance(model, str)}),
            "recorded_model_usage": totals, "recorded_wall_seconds": sum(row.get("elapsed_seconds") or 0 for row in rows),
            "monetary_cost": None, "monetary_cost_note": "No inferred bill; recorded tokens/requests may omit interrupted or unreported requests.",
            "experience_reports_available": sum(isinstance(row.get("experience_report"), dict) for row in rows),
            "false_block_rate": None, "causal_tool_calls_saved": None}


def summarize(root):
    root = Path(root).resolve()
    plan = read_optional(root / "ablation-plan.json")
    protocol = plan.get("protocol", {})
    if (protocol.get("version") != PROTOCOL_VERSION or canonical_sha256(protocol) != plan.get("protocol_sha256")
            or Path(plan.get("output_root", "")).resolve() != root):
        raise ValueError("Missing/invalid protocol or moved output root; do not guess artifact provenance")
    rows = {mode: [] for mode in MODES}
    by_key = {(job["mode"], job["id"]): job for job in jobs(plan)}
    for mode in MODES:
        for identity in protocol["expected_ids"]:
            rows[mode].append(collect_row(root, by_key[(mode, identity)]))
    return {"protocol_sha256": plan["protocol_sha256"], "metric_version": METRIC_VERSION,
            "expected_ids": protocol["expected_ids"], "arms": {mode: aggregate(rows[mode]) for mode in MODES},
            "tasks": rows, "official_evaluation": False,
            "interpretation": ["All planned tasks/arms remain in the denominator, including failures and missing results.",
                "Incomplete accounting produces null full-cohort metrics, not exclusion or zero imputation.",
                "Success requires official grading: local validation/submission does not establish resolved.",
                "Interaction rounds are original CLI feedback batches, not model calls.",
                "Redundancy remains cli-comparison-v1 same command/state/output repeat proxy; necessary re-verification can count.",
                "Experience rejection/gating counters are diagnostics, not saved actual tool calls or a false-block rate.",
                "This small one-run development ablation is descriptive, not a causal improvement or multi-seed claim.",
                "Scheduling seed changes execution order only; it does not resume a model or control provider sampling."]}


def parser():
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    result.add_argument("--task-manifest", type=Path)
    result.add_argument("--output-root", type=Path, required=True)
    result.add_argument("--python", type=Path, default=Path(sys.executable))
    result.add_argument("--task-python", type=Path)
    result.add_argument("--model", default="deepseek-flash")
    result.add_argument("--base-url", default="https://api.deepseek.com")
    result.add_argument("--temperature", type=float, default=0.2)
    result.add_argument("--top-p", type=float)
    result.add_argument("--reasoning-effort", choices=("low", "high", "max"), default="high")
    result.add_argument("--max-iterations", type=int, default=24)
    result.add_argument("--max-tool-calls", type=int, default=80)
    result.add_argument("--max-commands-per-action", type=int, default=6)
    result.add_argument("--task-timeout", type=float, default=14400)
    result.add_argument("--schedule-seed", type=int, default=20260921)
    result.add_argument("--expected-protocol-sha256", help="Optional hash from a reviewed dry plan; reject changes before execution")
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Explicitly allow paid model calls; fresh output only")
    mode.add_argument("--summarize", action="store_true", help="Read saved artifacts only; no model calls or grading")
    mode.add_argument("--dry-run", action="store_true", help="Default: print reproducible plan only, without creating outputs")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.summarize:
            print(json.dumps(summarize(args.output_root), ensure_ascii=False, indent=2))
            return 0
        if not args.task_manifest:
            raise ValueError("--task-manifest is required for planning/execution")
        plan = build_plan(args)
        if args.expected_protocol_sha256 and args.expected_protocol_sha256 != plan["protocol_sha256"]:
            raise ValueError("Reviewed protocol hash differs; inspect a new dry plan before execution")
        if not args.execute:
            plan["commands"] = [[plan["protocol"]["python"], str(ROOT / "run_notebook.py"), *job["argv"]] for job in jobs(plan)]
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        return execute_plan(plan)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[experience ablation] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
