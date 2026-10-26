#!/usr/bin/env python3
"""Run the frozen four-arm v14 ablation on 45 SWE-bench Pro HARD tasks."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path("/mnt/lizh639/bestfgs-runs/swepro-v2-hard45-v14-ablation-20260924")
CONTROL = ROOT / "control"
SOURCE_ROOT = Path("/mnt/lizh639/bestfgs-runs/swepro-v2-hard50-v13-20260924")
SOURCE_CONTROL = SOURCE_ROOT / "control" / "paired_hard50_control.py"
CODE = Path("/mnt/lizh639/branching-memory-v14")
PYTHON = Path("/mnt/lizh639/envs/bestfgs/bin/python")
AGENT_ENV = Path("/mnt/lizh639/envs/bestfgs")
MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
HOSTS = ("lizh639-aa91", "lizh639-8e64")
METHODS = ("raw", "memory_only", "search_only", "bestfgs")
TERMINAL_METHOD_STATES = frozenset(("completed", "model_output_failure"))
MAX_METHOD_ATTEMPTS = 3
MAX_GUARD_RECOVERIES = 20
SELECTION_SHA256 = "e4f9cc31442d418cc0d4cdacb830603b053497c5b1a49c97f167a8f369bcccdb"
SOURCE_SELECTION_SHA256 = "381f9e131112c2779c61ad24afc678755b3c0147ef050ca4c328d301defeb7fd"
SOURCE_CONTROL_SHA256 = "158a2059e713b6df46fc657527edb5fb5c10750e95e585c6de17af4d73e47bb6"
CODE_ARCHIVE_SHA256 = "035397290233db3b48d14983135275b0a1fb34a65c7f45f9dab8788f3a87f6ad"


def load_source_control():
    if hashlib.sha256(SOURCE_CONTROL.read_bytes()).hexdigest() != SOURCE_CONTROL_SHA256:
        raise RuntimeError("Frozen HARD-50 cache controller changed")
    spec = importlib.util.spec_from_file_location("swepro_hard50_source_control", SOURCE_CONTROL)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen HARD-50 cache controller")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOURCE = load_source_control()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_ids() -> list[str]:
    path = SOURCE_ROOT / "control" / "hard50_ids.txt"
    values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(values) != 50 or len(set(values)) != 50 or digest(path) != SOURCE_SELECTION_SHA256:
        raise ValueError("Frozen source HARD-50 selection changed")
    return values


def selected_ids() -> list[str]:
    path = CONTROL / "hard45_ids.txt"
    values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(values) != 45 or len(set(values)) != 45 or digest(path) != SELECTION_SHA256:
        raise ValueError("Frozen HARD-45 selection is missing, duplicated or changed")
    if not set(values).issubset(source_ids()):
        raise ValueError("HARD-45 selection is not a subset of the frozen HARD-50 cache population")
    expected = sorted(
        source_ids(),
        key=lambda value: (hashlib.sha256(("v14-hard45\0" + value).encode()).hexdigest(), value),
    )[:45]
    if values != expected:
        raise ValueError("HARD-45 selection does not match the preregistered SHA-256 rule")
    return values


def assignments(index: int) -> list[str]:
    selected = set(selected_ids())
    source_order = sorted(source_ids(), key=lambda value: (hashlib.sha256(value.encode()).hexdigest(), value))
    return [identity for position, identity in enumerate(source_order)
            if position % 2 == index and identity in selected]


def assignment_index(identity: str) -> int:
    for index in (0, 1):
        if identity in assignments(index):
            return index
    raise ValueError(f"Task is outside the frozen selection: {identity}")


def method_order(identity: str) -> list[str]:
    # All 24 permutations are used in a deterministic cycle over the frozen list.
    # This balances order without observing any outcome.
    permutations = tuple(itertools.permutations(METHODS))
    return list(permutations[selected_ids().index(identity) % len(permutations)])


def verify_model(key: str) -> None:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "temperature": 0,
        "max_tokens": 4,
        "stream": False,
    }).encode()
    request = urllib.request.Request(
        BASE_URL + "/chat/completions", data=payload, method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        exc.read(1200)
        raise ValueError(f"DeepSeek authentication/model check failed: HTTP {exc.code}") from None
    if not result.get("choices"):
        raise ValueError("DeepSeek authentication/model check returned no choices")


def process_alive(record: dict | None) -> bool:
    if not record:
        return False
    try:
        os.kill(int(record["pid"]), 0)
        return True
    except (OSError, KeyError, TypeError, ValueError):
        return False


def state_documents(index: int) -> list[dict]:
    result = []
    for identity in assignments(index):
        path = ROOT / "states" / f"{identity}.json"
        if path.is_file():
            result.append(json.loads(path.read_text(encoding="utf-8")))
    return result


def validate_ready(*, require_images: bool = False) -> dict:
    ids = selected_ids()
    problems = []
    archive = CONTROL / "branching-memory-v14.tar.gz"
    if not archive.is_file() or digest(archive) != CODE_ARCHIVE_SHA256:
        problems.append("frozen v14 archive missing or changed")
    if not CODE.is_dir() or not (CODE / "VALIDATION_V14.json").is_file():
        problems.append("deployed v14 tree missing")
    else:
        receipt = json.loads((CODE / "VALIDATION_V14.json").read_text(encoding="utf-8"))
        if receipt.get("result", {}).get("status") != "passed":
            problems.append("v14 validation receipt is not passed")
    metadata = SOURCE_ROOT / "control" / "agent-metadata"
    if not metadata.is_dir() or any(not (metadata / identity / "instruction.md").is_file() for identity in ids):
        problems.append("sanitized task instructions missing")
    for executable in ("git", "proot", "umoci"):
        if shutil.which(executable) is None:
            problems.append(f"required runtime is missing: {executable}")
    hostname = os.uname().nodename
    test_exit = ROOT / f"v14-linux-tests-{hostname}.exit"
    if not test_exit.is_file() or test_exit.read_text().strip() != "0":
        problems.append(f"v14 Linux regression has not passed on {hostname}")
    cached = sum((SOURCE_ROOT / "cache-ready" / identity).is_file() for identity in ids)
    if require_images and cached != len(ids):
        problems.append(f"official image cache incomplete ({cached}/{len(ids)})")
    workers = []
    for index, expected_hostname in enumerate(HOSTS):
        launch_path = ROOT / "launch" / f"worker-{index}.json"
        launch = json.loads(launch_path.read_text()) if launch_path.is_file() else None
        states = state_documents(index)
        methods = {method: 0 for method in METHODS}
        for state in states:
            for method in METHODS:
                if state.get("methods", {}).get(method, {}).get("status") in TERMINAL_METHOD_STATES:
                    methods[method] += 1
        workers.append({
            "index": index, "hostname": expected_hostname, "alive": process_alive(launch),
            "assigned": len(assignments(index)), "completed_tasks": sum(
                item.get("status") == "completed" for item in states),
            "recorded_tasks": len(states), "terminal_method_runs": methods, "launch": launch,
        })
    return {"ready": not problems, "problems": problems, "cached_images": cached,
            "selection_count": len(ids), "total_method_runs": len(ids) * len(METHODS),
            "model": MODEL, "methods": list(METHODS), "workers": workers}


def wait_for_image(identity: str, index: int, timeout: int = 24 * 60 * 60) -> None:
    marker = SOURCE_ROOT / "cache-ready" / identity
    deadline = time.monotonic() + timeout
    while not marker.is_file():
        atomic_json(ROOT / "health" / f"worker-{index}.json", {
            "worker": index, "hostname": HOSTS[index], "status": "waiting_for_image",
            "task": identity, "updated_at": time.time(),
        })
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Official image was not cached within {timeout} seconds: {identity}")
        cache = subprocess.run(["pgrep", "-f", f"cache_hard50.py --index {index}"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if cache.returncode != 0:
            raise RuntimeError(f"Image cache worker {index} stopped before preparing {identity}")
        time.sleep(30)


def prepare_task(identity: str) -> tuple[Path, str, str]:
    # Reuse the frozen HARD-50 OCI cache and bundle builder; no gold patch or
    # verifier is copied into the agent-visible metadata.
    rootfs, workspace, commit = SOURCE.prepare_task(identity)
    target = rootfs / "opt/bestfgs-v14"
    if not target.exists():
        shutil.copytree(CODE, target, symlinks=True)
    if not (target / "VALIDATION_V14.json").is_file():
        raise ValueError(f"Frozen v14 code missing inside task image: {identity}")
    return rootfs, workspace, commit


def common_agent_args(method: str) -> list[str]:
    arguments = [
        "--provider", "deepseek", "--model", MODEL, "--base-url", BASE_URL,
        "--api-key-env", "DEEPSEEK_API_KEY", "--temperature", "0.2",
        "--reasoning-effort", "high", "--solve-reasoning-effort", "max",
        "--max-iterations", "33", "--max-tool-calls", "108",
        "--max-commands-per-action", "4", "--budget-multiplier", "1",
        "--no-adaptive-budget", "--success-judge-mode", "off", "--comparison-metrics",
        "--model-timeout", "90", "--model-max-wall-time", "600",
        "--model-request-attempts", "5", "--model-parse-attempts", "3",
    ]
    if method == "raw":
        arguments.extend(("--engine", "evidence"))
    return arguments


def reset_workspace(rootfs: Path, workspace: str, commit: str) -> None:
    SOURCE.reset_workspace(rootfs, workspace, commit)


def export_output(output_host: Path, method: str, identity: str) -> Path:
    export = ROOT / "exports" / method / identity
    if export.exists():
        if not export.resolve().is_relative_to((ROOT / "exports").resolve()):
            raise ValueError("Refusing to replace export outside experiment root")
        shutil.rmtree(export)
    shutil.copytree(output_host, export, symlinks=True)
    return export


def run_method(identity: str, method: str, rootfs: Path, workspace: str,
               commit: str, previous: dict | None) -> dict:
    attempts = int((previous or {}).get("attempt_count", 0))
    instruction = (SOURCE_ROOT / "control/agent-metadata" / identity / "instruction.md").read_text(encoding="utf-8")
    manifest_host = rootfs / "opt/swepro-task/manifest-v14.json"
    atomic_json(manifest_host, {
        "schema_version": 1, "benchmark": "swebench",
        "tasks": [{"id": identity, "goal": instruction, "workspace": workspace,
                   "base_commit": commit, "prepared_commit": commit, "success_criteria": [],
                   "constraints": ["Do not use external solutions, web search, future Git history, or verifier files."]}],
    })
    inside_output = f"/bestfgs-v14-results/{method}/{identity}"
    output_host = rootfs / inside_output.lstrip("/")
    log = ROOT / "logs" / f"{identity}.{method}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    last_state = {}
    while attempts < MAX_METHOD_ATTEMPTS:
        attempts += 1
        reset_workspace(rootfs, workspace, commit)
        arguments = [
            "proot", "-R", str(rootfs), "-b", f"{AGENT_ENV}:/opt/agent-python", "-w", "/",
            "/usr/bin/env", "PATH=/opt/agent-python/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME=/root", "LANG=C.UTF-8", "PYTHONUNBUFFERED=1", "PYTHONDONTWRITEBYTECODE=1",
            "PYTHONPATH=/opt/bestfgs-v14/src", "OMP_NUM_THREADS=1", "OPENBLAS_NUM_THREADS=1",
            "DEEPSEEK_API_KEY=" + os.environ["DEEPSEEK_API_KEY"],
            "/opt/agent-python/bin/python", "/opt/bestfgs-v14/run_notebook.py",
            "--task-manifest", "/opt/swepro-task/manifest-v14.json",
            "--output-root", inside_output, "--python", "/opt/agent-python/bin/python",
            "--task-timeout", "3000", "--method", method,
        ]
        if (output_host / "notebook-run.json").is_file():
            arguments.append("--resume")
        arguments.extend(("--", *common_agent_args(method)))
        with log.open("ab", buffering=0) as stream:
            stream.write((f"\n[v14 scheduler] attempt {attempts}/{MAX_METHOD_ATTEMPTS}\n").encode())
            try:
                code = subprocess.run(arguments, stdout=stream, stderr=subprocess.STDOUT,
                                      timeout=3300).returncode
            except subprocess.TimeoutExpired:
                code = 124
        task_state = output_host / identity / "status.json"
        last_state = json.loads(task_state.read_text()) if task_state.is_file() else {
            "status": "error", "error": f"runner exit {code} without status.json"}
        if last_state.get("status") == "completed":
            export = export_output(output_host, method, identity)
            return {"method": method, "status": "completed", "attempt_count": attempts,
                    "output": str(export), "patch_sha256": last_state.get("patch_sha256"),
                    "submitted": last_state.get("submitted"), "stop_reason": last_state.get("stop_reason")}
        if last_state.get("model_output_failure") is True:
            export = export_output(output_host, method, identity)
            return {"method": method, "status": "model_output_failure", "attempt_count": attempts,
                    "output": str(export), "patch_sha256": last_state.get("patch_sha256"),
                    "submitted": False, "stop_reason": last_state.get("stop_reason"),
                    "error": last_state.get("error")}
        if attempts < MAX_METHOD_ATTEMPTS:
            time.sleep(min(120, 20 * attempts))
    export = export_output(output_host, method, identity) if output_host.exists() else None
    return {"method": method, "status": "infrastructure_error", "attempt_count": attempts,
            "output": str(export) if export else None, "submitted": False,
            "stop_reason": last_state.get("stop_reason"), "error": last_state.get("error", "retry limit reached")}


def worker(index: int) -> None:
    if os.uname().nodename != HOSTS[index]:
        raise ValueError("Worker launched on the wrong CubeStudio container")
    readiness = validate_ready(require_images=False)
    if not readiness["ready"]:
        raise ValueError("Experiment is not ready: " + "; ".join(readiness["problems"]))
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise ValueError("Missing DEEPSEEK_API_KEY")
    for identity in assignments(index):
        path = ROOT / "states" / f"{identity}.json"
        state = json.loads(path.read_text()) if path.is_file() else {
            "id": identity, "worker": index, "hostname": HOSTS[index], "methods": {}}
        if state.get("status") == "completed":
            continue
        state.update(status="waiting_for_image", method_order=method_order(identity), updated_at=time.time())
        atomic_json(path, state)
        wait_for_image(identity, index)
        state.update(status="preparing", updated_at=time.time())
        atomic_json(path, state)
        rootfs, workspace, commit = prepare_task(identity)
        for method in method_order(identity):
            previous = state["methods"].get(method)
            if previous and previous.get("status") in TERMINAL_METHOD_STATES:
                continue
            if previous and int(previous.get("attempt_count", 0)) >= MAX_METHOD_ATTEMPTS:
                continue
            state.update(status=f"running_{method}", updated_at=time.time())
            atomic_json(path, state)
            state["methods"][method] = run_method(
                identity, method, rootfs, workspace, commit, previous)
            atomic_json(path, state)
        terminal = all(state["methods"].get(method, {}).get("status") in TERMINAL_METHOD_STATES
                       for method in METHODS)
        state.update(status="completed" if terminal else "incomplete", updated_at=time.time())
        atomic_json(path, state)
        atomic_json(ROOT / "health" / f"worker-{index}.json", {
            "worker": index, "hostname": HOSTS[index], "status": state["status"],
            "last_task": identity, "updated_at": time.time(),
        })


def retryable_work(index: int) -> bool:
    for identity in assignments(index):
        path = ROOT / "states" / f"{identity}.json"
        if not path.is_file():
            return True
        state = json.loads(path.read_text())
        for method in METHODS:
            record = state.get("methods", {}).get(method)
            if not record or (record.get("status") not in TERMINAL_METHOD_STATES
                              and int(record.get("attempt_count", 0)) < MAX_METHOD_ATTEMPTS):
                return True
    return False


def guard(index: int) -> None:
    recoveries = 0
    while True:
        try:
            worker(index)
        except Exception as exc:
            atomic_json(ROOT / "health" / f"worker-{index}.json", {
                "worker": index, "hostname": HOSTS[index], "status": "guard_recovery",
                "error": str(exc), "recovery": recoveries, "updated_at": time.time(),
            })
        if not retryable_work(index):
            return
        recoveries += 1
        if recoveries > MAX_GUARD_RECOVERIES:
            atomic_json(ROOT / "health" / f"worker-{index}.json", {
                "worker": index, "hostname": HOSTS[index], "status": "guard_limit_reached",
                "recoveries": recoveries - 1, "updated_at": time.time(),
            })
            return
        time.sleep(min(300, 30 * recoveries))


def launch(index: int) -> None:
    if os.uname().nodename != HOSTS[index]:
        raise ValueError("Launch command sent to the wrong CubeStudio container")
    readiness = validate_ready(require_images=False)
    if not readiness["ready"]:
        raise ValueError("Experiment is not ready: " + "; ".join(readiness["problems"]))
    document = json.load(sys.stdin)
    key = str(document.get("key", "")).strip()
    if not key or re.search(r"\s", key):
        raise ValueError("Invalid DeepSeek key")
    launch_path = ROOT / "launch" / f"worker-{index}.json"
    if launch_path.exists():
        old = json.loads(launch_path.read_text())
        if process_alive(old):
            raise ValueError("Worker is already active")
        raise ValueError("A stale launch record exists; inspect before retrying")
    verify_model(key)
    console = ROOT / "logs" / f"worker-{index}.console.log"
    console.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, DEEPSEEK_API_KEY=key, PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
    with console.open("ab", buffering=0) as stream:
        process = subprocess.Popen(
            [str(PYTHON), str(Path(__file__).resolve()), "guard", "--index", str(index)],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
            env=environment, start_new_session=True, close_fds=True)
    atomic_json(launch_path, {"worker": index, "pid": process.pid, "hostname": HOSTS[index],
                              "model": MODEL, "started_at": time.time(),
                              "credential_persisted": False, "startup_auth_requests": 1,
                              "console": str(console)})
    print(json.dumps({"launched": True, "worker": index, "pid": process.pid,
                      "console": str(console)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("validate", "status", "launch", "worker", "guard"))
    parser.add_argument("--index", type=int, choices=(0, 1), default=0)
    parser.add_argument("--require-images", action="store_true")
    args = parser.parse_args()
    if args.action in {"validate", "status"}:
        print(json.dumps(validate_ready(require_images=args.require_images), ensure_ascii=False, indent=2))
    elif args.action == "launch":
        launch(args.index)
    elif args.action == "guard":
        guard(args.index)
    else:
        worker(args.index)


if __name__ == "__main__":
    main()
