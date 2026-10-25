#!/usr/bin/env python3
"""Prepare, launch, resume and inspect the paired SWE-bench Pro V2 HARD-50 run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path("/mnt/lizh639/bestfgs-runs/swepro-v2-hard50-v13-20260924")
CONTROL = ROOT / "control"
CODE = Path("/mnt/lizh639/BestFGS-branching-memory-v13")
PYTHON = Path("/mnt/lizh639/envs/bestfgs/bin/python")
AGENT_ENV = Path("/mnt/lizh639/envs/bestfgs")
MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
HOSTS = ("lizh639-aa91", "lizh639-8e64")
SELECTION_SHA256 = "381f9e131112c2779c61ad24afc678755b3c0147ef050ca4c328d301defeb7fd"
CODE_ARCHIVE_SHA256 = "008fcdf83dd2c248d1f78d1cc907d24d80ffd5a2ace20a987c141d17e6d04391"


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_ids() -> list[str]:
    path = CONTROL / "hard50_ids.txt"
    ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(ids) != 50 or len(set(ids)) != 50 or digest(path) != SELECTION_SHA256:
        raise ValueError("Frozen HARD-50 selection is missing, duplicated or changed")
    return ids


def assignments(index: int) -> list[str]:
    ordered = sorted(selected_ids(), key=lambda value: (hashlib.sha256(value.encode()).hexdigest(), value))
    return ordered[index::2]


def oci_tag(identity: str) -> str:
    return "task-" + hashlib.sha256(identity.encode()).hexdigest()[:32]


def assignment_index(identity: str) -> int:
    if identity in assignments(0):
        return 0
    if identity in assignments(1):
        return 1
    raise ValueError(f"Task is outside the frozen selection: {identity}")


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


def validate_ready(*, require_images: bool = True) -> dict:
    ids = selected_ids()
    archive = CONTROL / "branching-memory-v13.tar.gz"
    metadata = CONTROL / "agent-metadata"
    problems = []
    if not archive.is_file() or digest(archive) != CODE_ARCHIVE_SHA256:
        problems.append("frozen v13 archive missing or changed")
    if not CODE.is_dir():
        problems.append("deployed v13 tree missing")
    if not metadata.is_dir() or any(not (metadata / identity / "instruction.md").is_file() for identity in ids):
        problems.append("sanitized task instructions missing")
    for executable in ("git", "proot", "umoci"):
        if shutil.which(executable) is None:
            problems.append(f"required runtime is missing: {executable}")
    test_exit = ROOT / "v13-linux-tests.exit"
    if not test_exit.is_file() or test_exit.read_text().strip() != "0":
        problems.append("v13 Linux regression has not passed")
    cached = sum((ROOT / "cache-ready" / identity).is_file() for identity in ids)
    if require_images and (cached != 50 or not (ROOT / "IMAGE_CACHE_READY").is_file()):
        problems.append(f"official image cache incomplete ({cached}/50)")
    status = {"ready": not problems, "problems": problems, "cached_images": cached,
              "selection_count": len(ids), "model": MODEL, "workers": []}
    for index, hostname in enumerate(HOSTS):
        launch = ROOT / "launch" / f"worker-{index}.json"
        data = json.loads(launch.read_text()) if launch.is_file() else None
        alive = False
        if data:
            try:
                os.kill(int(data["pid"]), 0)
                alive = True
            except (OSError, KeyError, ValueError):
                pass
        states = []
        for identity in assignments(index):
            path = ROOT / "states" / f"{identity}.json"
            if path.is_file():
                states.append(json.loads(path.read_text()))
        status["workers"].append({"index": index, "hostname": hostname, "alive": alive,
                                  "assigned": 25,
                                  "completed_tasks": sum(item.get("status") == "completed" for item in states),
                                  "recorded_tasks": len(states), "launch": data})
    return status


def clean_partial(path: Path) -> None:
    if path.exists():
        if not path.resolve().is_relative_to((ROOT / "bundles").resolve()):
            raise ValueError("Refusing to remove a partial path outside the experiment")
        shutil.rmtree(path)


def wait_for_image(identity: str, index: int, *, timeout: int = 24 * 60 * 60) -> None:
    marker = ROOT / "cache-ready" / identity
    deadline = time.monotonic() + timeout
    while not marker.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Official image was not cached within {timeout} seconds: {identity}")
        cache = subprocess.run(
            ["pgrep", "-f", f"cache_hard50.py --index {index}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if cache.returncode != 0:
            raise RuntimeError(f"Image cache worker {index} stopped before preparing {identity}")
        time.sleep(30)


def prepare_task(identity: str) -> tuple[Path, str, str]:
    bundle = ROOT / "bundles" / identity
    rootfs = bundle / "rootfs"
    ready = bundle / "READY"
    if not ready.is_file():
        partial = bundle.with_name(bundle.name + ".partial")
        clean_partial(partial)
        partial.parent.mkdir(parents=True, exist_ok=True)
        layout = ROOT / f"oci-{assignment_index(identity)}"
        subprocess.run(["umoci", "unpack", "--image", f"{layout}:{oci_tag(identity)}", str(partial)], check=True)
        shutil.copy2("/etc/resolv.conf", partial / "rootfs/etc/resolv.conf")
        shutil.copytree(CODE, partial / "rootfs/opt/bestfgs-v13", symlinks=True)
        shutil.copytree(CONTROL / "agent-metadata" / identity,
                        partial / "rootfs/opt/swepro-task", symlinks=True)
        partial.replace(bundle)
        ready.touch()
    workspace = "/app" if (rootfs / "app/.git").is_dir() else "/testbed"
    if not (rootfs / workspace.lstrip("/") / ".git").is_dir():
        raise ValueError(f"No clean Git workspace in official image: {identity}")
    probe = subprocess.run(
        ["chroot", str(rootfs), "/bin/bash", "-lc",
         f"cd {workspace} && test -z \"$(git status --porcelain)\" && git rev-parse HEAD"],
        check=True, capture_output=True, text=True, timeout=120,
    )
    commit = probe.stdout.strip().splitlines()[-1]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"Invalid base commit in official image: {identity}")
    return rootfs, workspace, commit


def method_args(method: str) -> list[str]:
    common = [
        "--provider", "deepseek", "--model", MODEL, "--base-url", BASE_URL,
        "--api-key-env", "DEEPSEEK_API_KEY", "--temperature", "0.2",
        "--reasoning-effort", "high", "--solve-reasoning-effort", "max",
        "--max-iterations", "33", "--max-tool-calls", "108",
        "--max-commands-per-action", "4", "--budget-multiplier", "1",
        "--no-adaptive-budget", "--success-judge-mode", "off", "--comparison-metrics",
        "--model-timeout", "90", "--model-max-wall-time", "600",
        "--model-request-attempts", "5", "--model-parse-attempts", "3",
    ]
    if method == "bestfgs":
        return common + ["--engine", "graph", "--experience-mode", "conditioned",
                         "--blocking-memory", "off"]
    return common + ["--engine", "evidence", "--experience-mode", "off",
                     "--blocking-memory", "off", "--disable-evidence-branching"]


def reset_workspace(rootfs: Path, workspace: str, commit: str) -> None:
    command = f"cd {shlex.quote(workspace)} && git reset --hard {shlex.quote(commit)} && git clean -fdx"
    subprocess.run(["chroot", str(rootfs), "/bin/bash", "-lc", command],
                   check=True, capture_output=True, text=True, timeout=300)


def run_method(identity: str, method: str, rootfs: Path, workspace: str, commit: str) -> dict:
    instruction = (CONTROL / "agent-metadata" / identity / "instruction.md").read_text(encoding="utf-8")
    manifest_host = rootfs / "opt/swepro-task/manifest.json"
    atomic_json(manifest_host, {
        "schema_version": 1, "benchmark": "swebench",
        "tasks": [{"id": identity, "goal": instruction, "workspace": workspace,
                   "base_commit": commit, "prepared_commit": commit,
                   "success_criteria": [],
                   "constraints": ["Do not use external solutions, web search, future Git history, or verifier files."]}],
    })
    inside_output = f"/bestfgs-results/{method}/{identity}"
    output_host = rootfs / inside_output.lstrip("/")
    arguments = [
        "proot", "-R", str(rootfs), "-b", f"{AGENT_ENV}:/opt/agent-python", "-w", "/",
        "/usr/bin/env",
        "PATH=/opt/agent-python/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME=/root", "LANG=C.UTF-8", "PYTHONUNBUFFERED=1", "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONPATH=/opt/bestfgs-v13/src", "OMP_NUM_THREADS=1", "OPENBLAS_NUM_THREADS=1",
        "DEEPSEEK_API_KEY=" + os.environ["DEEPSEEK_API_KEY"],
        "/opt/agent-python/bin/python", "/opt/bestfgs-v13/run_notebook.py",
        "--task-manifest", "/opt/swepro-task/manifest.json",
        "--output-root", inside_output, "--python", "/opt/agent-python/bin/python",
        "--task-timeout", "3000", "--method", method,
    ]
    if (output_host / "notebook-run.json").is_file():
        arguments.append("--resume")
    arguments.extend(["--", *method_args(method)])
    log = ROOT / "logs" / f"{identity}.{method}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab", buffering=0) as stream:
        code = subprocess.run(arguments, stdout=stream, stderr=subprocess.STDOUT, timeout=3300).returncode
    if code != 0:
        raise RuntimeError(f"{method} runner failed with exit code {code}; see {log}")
    task_state = output_host / identity / "status.json"
    state = json.loads(task_state.read_text())
    if state.get("status") != "completed":
        raise RuntimeError(f"{method} did not complete normally: {state.get('status')}")
    export = ROOT / "exports" / method / identity
    if export.exists():
        shutil.rmtree(export)
    shutil.copytree(output_host, export, symlinks=True)
    return {"method": method, "status": "completed", "output": str(export),
            "patch_sha256": state.get("patch_sha256"),
            "submitted": state.get("submitted"), "stop_reason": state.get("stop_reason")}


def worker(index: int) -> None:
    if os.uname().nodename != HOSTS[index]:
        raise ValueError("Worker launched on the wrong CubeStudio container")
    validate = validate_ready(require_images=False)
    if not validate["ready"]:
        raise ValueError("Experiment is not ready: " + "; ".join(validate["problems"]))
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise ValueError("Missing DEEPSEEK_API_KEY")
    for identity in assignments(index):
        state_path = ROOT / "states" / f"{identity}.json"
        state = json.loads(state_path.read_text()) if state_path.is_file() else {}
        if state.get("status") == "completed":
            continue
        state = {"id": identity, "worker": index, "hostname": HOSTS[index],
                 "status": "preparing", "methods": state.get("methods", {}),
                 "updated_at": time.time()}
        atomic_json(state_path, state)
        try:
            state.update(status="waiting_for_image", updated_at=time.time())
            atomic_json(state_path, state)
            wait_for_image(identity, index)
            state.update(status="preparing", updated_at=time.time())
            atomic_json(state_path, state)
            rootfs, workspace, commit = prepare_task(identity)
            order = ["bestfgs", "raw"] if int(hashlib.sha256(identity.encode()).hexdigest(), 16) % 2 == 0 else ["raw", "bestfgs"]
            for method in order:
                if state["methods"].get(method, {}).get("status") == "completed":
                    continue
                reset_workspace(rootfs, workspace, commit)
                state.update(status=f"running_{method}", updated_at=time.time())
                atomic_json(state_path, state)
                state["methods"][method] = run_method(identity, method, rootfs, workspace, commit)
                atomic_json(state_path, state)
            state.update(status="completed", updated_at=time.time())
            atomic_json(state_path, state)
        except Exception as exc:
            state.update(status="infrastructure_error", error=str(exc), updated_at=time.time())
            atomic_json(state_path, state)
            raise


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
        try:
            os.kill(int(old["pid"]), 0)
        except (OSError, KeyError, ValueError):
            raise ValueError("A stale launch record exists; inspect before retrying")
        raise ValueError("Worker is already active")
    verify_model(key)
    console = ROOT / "logs" / f"worker-{index}.console.log"
    console.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, DEEPSEEK_API_KEY=key, PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
    with console.open("ab", buffering=0) as stream:
        process = subprocess.Popen([str(PYTHON), str(CONTROL / "paired_hard50_control.py"), "worker", "--index", str(index)],
                                   stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                   env=environment, start_new_session=True, close_fds=True)
    atomic_json(launch_path, {"worker": index, "pid": process.pid, "hostname": HOSTS[index],
                              "model": MODEL, "started_at": time.time(),
                              "credential_persisted": False, "startup_auth_requests": 1,
                              "console": str(console)})
    print(json.dumps({"launched": True, "worker": index, "pid": process.pid, "console": str(console)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("validate", "status", "launch", "worker"))
    parser.add_argument("--index", type=int, choices=(0, 1), default=0)
    parser.add_argument("--allow-incomplete-images", action="store_true")
    args = parser.parse_args()
    if args.action in {"validate", "status"}:
        require_images = args.action == "validate" and not args.allow_incomplete_images
        print(json.dumps(validate_ready(require_images=require_images), ensure_ascii=False, indent=2))
    elif args.action == "launch":
        launch(args.index)
    else:
        worker(args.index)


if __name__ == "__main__":
    main()
