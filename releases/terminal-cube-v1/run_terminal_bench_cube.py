"""Two-task, relocated-file Cube-Studio pilot. Not an official Harbor evaluator."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

from benchmark_runtime import atomic_write_json, implementation_sha256
from benchmark_splits import frozen_terminal_task_names, reject_frozen_overlap
import run_notebook

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "terminal_cube"
PILOT = ("polyglot-c-py", "openssl-selfsigned-cert")
METHODS = ("bestfgs", "raw")
LIMITATIONS = [
    "Public instructions relocated from /app to the current workspace; original instructions retained.",
    "Notebook system packages differ from the original task images.",
    "File snapshots cannot reset processes, system packages, absolute paths or external services.",
    "Public smoke checks are incomplete diagnostics, not official Terminal-Bench rewards.",
    "Two dependency-compatible tasks selected for integration testing; not a representative sample.",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locked_sources() -> dict:
    path = DATA / "dataset-lock.json"
    if sha(path) != (DATA / "dataset-lock.sha256").read_text().strip():
        raise ValueError("Dataset lock checksum mismatch")
    lock = json.loads(path.read_text())
    tasks = lock["tasks"]
    ids = [t["id"] for t in tasks]
    frozen = set(frozen_terminal_task_names(bare=True))
    if len(ids) != 89 or len(set(ids)) != 89 or not frozen <= set(ids):
        raise ValueError("Expected the pinned 89-task dataset including all 9 frozen tasks")
    for task in tasks:
        if task["frozen"] != (task["id"] in frozen) or not re.fullmatch(r"sha256:[a-f0-9]{64}", task["ref"]):
            raise ValueError("Invalid dataset pin or split")
    reject_frozen_overlap(PILOT, benchmark="terminal-bench", allow_frozen_test_set=False)
    for name in PILOT:
        source = DATA / "public_tasks" / name
        receipt = json.loads((source / "source-lock.json").read_text())
        expected = next(t for t in tasks if t["id"] == name)
        if receipt["id"] != name or receipt["package_ref"] != expected["ref"]:
            raise ValueError("Pilot source does not match dataset lock")
        for file in ("instruction.md", "task.toml", "environment/Dockerfile"):
            if sha(source / file) != receipt["files"][file]:
                raise ValueError(f"Public source changed: {name}/{file}")
    return lock


def capture(argv: list[str], cwd: Path | None = None, timeout: int = 20) -> dict:
    try:
        result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout)
        return {"returncode": result.returncode, "stdout": result.stdout[:12000], "stderr": result.stderr[:2000]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "error": type(exc).__name__}


def preflight() -> dict:
    lock = locked_sources()
    commands = {
        "python": [sys.executable, "--version"],
        "python3": ["python3", "--version"],
        "gcc": ["gcc", "--version"],
        "openssl": ["openssl", "version"],
    }
    probes = {k: capture(v) for k, v in commands.items()}
    images = {n: tomllib.loads((DATA / "public_tasks" / n / "task.toml").read_text())["environment"].get("docker_image") for n in PILOT}
    ready = sys.version_info >= (3, 11) and platform.system() == "Linux" and all(p["returncode"] == 0 for p in probes.values())
    return {"schema_version": 1, "ready_for_portable_pilot": ready,
            "official_evaluation": False, "official_environment_ready": False,
            "host": platform.node(), "platform": platform.platform(),
            "dataset_count": len(lock["tasks"]), "development_count": 80, "frozen_count": 9,
            "pilot_tasks": list(PILOT), "original_images": images, "runtime": probes,
            "implementation_sha256": implementation_sha256(ROOT),
            "dataset_lock_sha256": sha(DATA / "dataset-lock.json"), "limitations": LIMITATIONS}


def prepare(output: Path) -> Path:
    """Fresh immutable seeds; this deliberately never executes a Dockerfile."""
    locked_sources()
    output.mkdir(parents=True, exist_ok=False)
    tasks = []
    for name in PILOT:
        seed = output / "seeds" / name
        seed.mkdir(parents=True)
        original = (DATA / "public_tasks" / name / "instruction.md").read_text()
        goal = original.replace("/app/", "./")
        if "/app" in goal:
            raise ValueError("Unexpected absolute path requires review")
        tasks.append({"id": name, "workspace": str(seed), "goal": goal,
                      "success_criteria": [], "constraints": [
                          "This is a relocated-file pilot. All task paths are relative to the current workspace.",
                          "Use the supplied Python, GCC and OpenSSL. Do not install system packages or modify paths outside the current workspace.",
                          "Keep all task outputs inside the current workspace; use relative paths in generated programs.",
                      ], "adaptation": {"path_mapping": {"/app/": "./"}, "official_evaluation": False},
                      "original_instruction_sha256": sha(DATA / "public_tasks" / name / "instruction.md")})
    manifest = output / "tasks.json"
    atomic_write_json(manifest, {"schema_version": 1, "benchmark": "terminal-bench", "tasks": tasks})
    return manifest


def safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError(f"Missing or external artifact: {relative}")
    return path


def public_probe(name: str, candidate: Path) -> dict:
    """Evaluate a disposable copy using public requirements; never mutate the candidate."""
    checks = {}
    try:
        # Reject external symlinks before copying a model-generated directory.
        for p in candidate.rglob("*"):
            if p.is_symlink() and not p.resolve().is_relative_to(candidate.resolve()):
                raise ValueError("Candidate includes external symlink")
        with tempfile.TemporaryDirectory(prefix="terminal-cube-probe-") as temp:
            work = Path(temp) / "candidate"
            shutil.copytree(candidate, work, symlinks=False)
            if name == "polyglot-c-py":
                source = safe_file(work, "polyglot/main.py.c")
                binary = Path(temp) / "cmain"
                build = capture(["gcc", str(source), "-o", str(binary)], cwd=work)
                checks["c_compilation"] = build["returncode"] == 0
                for n, value in ((0, 0), (1, 1), (2, 1), (10, 55), (20, 6765)):
                    for label, command in (("python", ["python3", str(source), str(n)]), ("c", [str(binary), str(n)])):
                        answer = capture(command, cwd=work, timeout=5)
                        checks[f"{label}_fib_{n}"] = answer["returncode"] == 0 and answer.get("stdout", "").strip() == str(value)
            elif name == "openssl-selfsigned-cert":
                paths = {n: safe_file(work, "ssl/" + n) for n in ("server.key", "server.crt", "server.pem", "verification.txt")}
                script = safe_file(work, "check_cert.py")
                cert = capture(["openssl", "x509", "-in", str(paths["server.crt"]), "-noout", "-subject", "-dates", "-fingerprint", "-sha256"])
                text = cert.get("stdout", "")
                checks["certificate_loads"] = cert["returncode"] == 0
                checks["certificate_subject"] = "DevOps Team" in text and "dev-internal.company.local" in text
                checks["key_permissions_600"] = (paths["server.key"].stat().st_mode & 0o777) == 0o600
                key = capture(["openssl", "rsa", "-in", str(paths["server.key"]), "-text", "-noout"])
                checks["rsa_2048"] = key["returncode"] == 0 and "2048 bit" in key.get("stdout", "")
                combined = paths["server.pem"].read_bytes()
                checks["combined_pem"] = paths["server.key"].read_bytes().strip() in combined and paths["server.crt"].read_bytes().strip() in combined
                verification = paths["verification.txt"].read_text()
                fingerprint = next((line.split("=", 1)[1] for line in text.splitlines() if "fingerprint=" in line.lower()), "")
                checks["verification_subject_and_fingerprint"] = "dev-internal.company.local" in verification and bool(fingerprint) and fingerprint in verification
                result = capture([sys.executable, str(script)], cwd=work)
                printed = result.get("stdout", "")
                checks["python_checker"] = result["returncode"] == 0 and "Certificate verification successful" in printed and "dev-internal.company.local" in printed and bool(re.search(r"\d{4}-\d{2}-\d{2}", printed))
            else:
                raise ValueError("Unsupported pilot task")
    except (OSError, ValueError) as exc:
        return {"public_smoke_passed": False, "checks": checks, "error": str(exc), "official_reward": None}
    return {"public_smoke_passed": bool(checks) and all(checks.values()), "checks": checks, "official_reward": None}


def report(output: Path, *, verify: bool = False) -> dict:
    rows = []
    for method in METHODS:
        for name in PILOT:
            status_path = output / method / name / "status.json"
            if not status_path.exists():
                rows.append({"method": method, "id": name, "status": "not_started", "official_reward": None})
                continue
            status = json.loads(status_path.read_text())
            row = {"method": method, "id": name, "status": status["status"], "official_reward": None}
            attempt = Path(status["attempt"]).resolve()
            if not attempt.is_relative_to((output / method / name).resolve()):
                raise ValueError("Attempt escapes output root")
            result_path = attempt / "agent-result.json"
            if result_path.is_file() and status["status"] == "completed":
                if sha(result_path) != status["result_sha256"]:
                    raise ValueError("Agent result hash changed")
                result = json.loads(result_path.read_text())
                row["agent_succeeded"] = result["succeeded"]
                row["stop_reason"] = result.get("stop_reason")
                row["metrics"] = result.get("comparison_metrics")
                candidate = result.get("best_workspace")
                probe_path = attempt / "public-smoke.json"
                if candidate and verify:
                    candidate = Path(candidate).resolve()
                    if not candidate.is_relative_to(attempt / "snapshots"):
                        raise ValueError("Candidate escapes attempt snapshots")
                    atomic_write_json(probe_path, public_probe(name, candidate))
                if probe_path.exists():
                    row.update(json.loads(probe_path.read_text()))
            rows.append(row)
    aggregates = {}
    for method in METHODS:
        selected = [r for r in rows if r['method'] == method]
        measured = [r['metrics'] for r in selected if isinstance(r.get('metrics'), dict) and r['metrics'].get('trace_complete')]
        tools = sum(m['tool_calls'] for m in measured)
        repeats = sum(m['redundant_tool_calls'] for m in measured)
        aggregates[method] = {
            'planned_tasks': len(selected), 'completed_tasks': sum(r['status'] == 'completed' for r in selected),
            'public_smoke_pass_count': sum(r.get('public_smoke_passed') is True for r in selected),
            'official_success_rate': None, 'complete_metric_traces': len(measured),
            'mean_interaction_rounds': sum(m['interaction_rounds'] for m in measured) / len(measured) if measured else None,
            'tool_calls': tools if measured else None, 'redundant_tool_calls': repeats if measured else None,
            'tool_call_redundancy_rate': repeats / tools if tools else None,
        }
    result = {"schema_version": 1, "official_evaluation": False, "scope": "two-task-relocated-file-pilot", "rows": rows, "summary": aggregates, "limitations": LIMITATIONS}
    atomic_write_json(output / "pilot-report.json", result)
    return result


def run(args) -> int:
    readiness = preflight()
    if not readiness["ready_for_portable_pilot"]:
        raise ValueError("Notebook runtime preflight failed")
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("Configure DEEPSEEK_API_KEY in this terminal before running; never put it in JSON or command arguments")
    output = args.output_root.resolve()
    manifest = prepare(output)
    atomic_write_json(output / "preflight.json", readiness)
    common = ["--provider", "deepseek", "--model", args.model, "--reasoning-effort", "high", "--solve-reasoning-effort", "high",
              "--max-iterations", "24", "--max-tool-calls", "80", "--max-commands-per-action", "4", "--no-adaptive-budget",
              "--success-judge-mode", "off", "--comparison-metrics"]
    atomic_write_json(output / "pilot-protocol.json", {"agent_args": common, "methods": METHODS, "task_timeout_seconds": 900, "official_evaluation": False,
                                                       "task_manifest_sha256": sha(manifest), "implementation_sha256": readiness["implementation_sha256"],
                                                       "dataset_lock_sha256": readiness["dataset_lock_sha256"], "selection_reason": "Existing notebook has Python, GCC and OpenSSL; no seed assets, services or dependency installation needed."})
    codes = []
    # Sequential methods avoid shared-host processes and resource contention within this pilot.
    for method in METHODS:
        print(f"[pilot] {method}: 2 tasks; see {output / method}", flush=True)
        codes.append(run_notebook.main(["--task-manifest", str(manifest), "--output-root", str(output / method), "--method", method,
                                       "--task-timeout", "900", "--", *common], expected_benchmark="terminal-bench"))
        report(output, verify=True)
        if codes[-1] == 130:
            return 130
    print(json.dumps(report(output), ensure_ascii=False, indent=2))
    return 2 if any(codes) else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "run", "report"))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--model", default="deepseek-flash")
    args = parser.parse_args(argv)
    try:
        if args.action == "preflight":
            result = preflight()
            if args.output_root:
                atomic_write_json(args.output_root / "preflight.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ready_for_portable_pilot"] else 2
        if args.output_root is None:
            parser.error("--output-root is required for run/report")
        if args.action == "report":
            print(json.dumps(report(args.output_root.resolve()), ensure_ascii=False, indent=2))
            return 0
        return run(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[cube pilot error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
