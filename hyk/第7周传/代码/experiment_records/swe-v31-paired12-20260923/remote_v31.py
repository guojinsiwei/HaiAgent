"""Prepare, launch and inspect two detached CubeStudio workers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

CODE = Path("/mnt/lizh639/BestFGS-blocking-memory-v12")
SETUP = Path("/mnt/lizh639/swe-v31-paired12-setup-20260923")
ROOT = Path("/mnt/lizh639/bestfgs-runs/swe-v31-paired12-20260923")
PREPARED = Path("/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen")
PYTHON = "/mnt/lizh639/envs/bestfgs/bin/python"
HOSTS = ("lizh639-aa91", "lizh639-8e64")
MODEL = "deepseek-v3.1"


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def valid_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.hostname or not parsed.hostname.endswith(".maas.aliyuncs.com")
            or not parsed.path.endswith("/compatible-mode/v1")):
        raise ValueError("Use the exact HTTPS Model Studio OpenAI-compatible Base URL; no key/query")
    return value


def verify_model(key: str, base_url: str) -> None:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "enable_thinking": False,
        "temperature": 0,
        "max_tokens": 4,
        "stream": False,
    }).encode()
    request = urllib.request.Request(
        base_url + "/chat/completions", data=payload, method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not print provider response bodies: some gateways echo request data.
        exc.read(1200)
        raise ValueError(f"Model Studio authentication/model check failed: HTTP {exc.code}") from None
    if not result.get("choices"):
        raise ValueError("Model Studio response has no choices")


def command(index: int, base_url: str) -> list[str]:
    return [
        PYTHON, str(SETUP / "run_comparison_v31.py"), "run",
        "--plan", str(ROOT / "task-plan.json"),
        "--prepared-root", str(PREPARED),
        "--output-root", str(ROOT / "results"),
        "--method", "both",
        "--model", MODEL,
        "--base-url", base_url,
        "--temperature", "0.6",
        "--top-p", "0.95",
        "--reasoning-effort", "high",
        "--max-iterations", "24",
        "--max-tool-calls", "80",
        "--max-commands", "6",
        "--task-timeout", "14400",
        "--shard-count", "2",
        "--shard-index", str(index),
    ]


def prepare() -> None:
    if ROOT.exists():
        raise ValueError("Experiment root already exists; refusing overwrite")
    subprocess.run([PYTHON, str(SETUP / "prepare_v31.py")], check=True)
    for index in (0, 1):
        subprocess.run(command(index, "https://placeholder.maas.aliyuncs.com/compatible-mode/v1")[:2]
                       + ["plan"] + command(index, "https://placeholder.maas.aliyuncs.com/compatible-mode/v1")[3:],
                       check=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


def launch(index: int) -> None:
    if os.uname().nodename != HOSTS[index]:
        raise ValueError("Wrong CubeStudio worker")
    document = json.load(sys.stdin)
    key = str(document.get("key", "")).strip()
    base_url = valid_base_url(str(document.get("base_url", "")))
    if not key or re.search(r"\s", key):
        raise ValueError("Invalid API key")
    status_path = ROOT / "launch" / f"worker-{index}.json"
    if status_path.exists():
        old = json.loads(status_path.read_text(encoding="utf-8"))
        try:
            os.kill(int(old["pid"]), 0)
        except (OSError, KeyError, ValueError):
            raise ValueError("Previous launch record exists but is not active; inspect before any retry")
        raise ValueError("Worker is already active")
    verify_model(key, base_url)
    log_path = ROOT / "logs" / f"worker-{index}.console.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, DASHSCOPE_API_KEY=key, PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    with log_path.open("ab", buffering=0) as stream:
        process = subprocess.Popen(command(index, base_url), stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, env=environment,
                                   start_new_session=True, close_fds=True)
    atomic_json(status_path, {"worker": index, "pid": process.pid, "hostname": HOSTS[index],
                              "started_at": time.time(), "model": MODEL,
                              "base_url_sha256": hashlib.sha256(base_url.encode()).hexdigest(),
                              "startup_auth_requests": 1,
                              "credential_persisted": False, "log": str(log_path)})
    print(json.dumps({"launched": True, "worker": index, "pid": process.pid, "log": str(log_path)}))


def status(index: int) -> None:
    launch_path = ROOT / "launch" / f"worker-{index}.json"
    worker_path = ROOT / "results" / "workers" / f"{index}.json"
    launch_data = json.loads(launch_path.read_text()) if launch_path.exists() else None
    process_alive = False
    if launch_data:
        try:
            os.kill(int(launch_data["pid"]), 0)
            process_alive = True
        except (OSError, KeyError, ValueError):
            pass
    states = []
    for method in ("bestfgs", "raw"):
        directory = ROOT / "results" / method / "states"
        if directory.is_dir():
            states.extend((method, json.loads(path.read_text()).get("status")) for path in directory.glob("*.json"))
    print(json.dumps({"worker": index, "process_alive": process_alive,
                      "worker_state": json.loads(worker_path.read_text()) if worker_path.exists() else None,
                      "completed": sum(state == "completed" for _, state in states),
                      "recorded": len(states), "method_states": states}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch", "status"))
    parser.add_argument("--index", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "launch":
        launch(args.index)
    else:
        status(args.index)


if __name__ == "__main__":
    main()
