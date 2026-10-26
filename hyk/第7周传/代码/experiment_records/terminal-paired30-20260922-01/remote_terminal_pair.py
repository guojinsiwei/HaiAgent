"""Launch and inspect one frozen TerminalBench pairing arm in remote tmux."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path("/mnt/lizh639/terminal-paired30-20260922-01")
PROJECT = ROOT / "BestFGS-terminal-paired-v10"
SELECTION = ROOT / "control" / "task-selection.json"
PYTHON = ROOT / "runtime" / "bin" / "python"
TMUX_CANDIDATES = (
    Path("/mnt/lizh639/envs/bestfgs/bin/tmux"),
    Path("/usr/bin/tmux"),
)
COMMON = (
    "run_terminal_bench_2random_tasks.py",
    "--environment", "daytona",
    "--sample-size", "30",
    "--sample-seed", "20260922",
    "--selection-file", str(SELECTION),
    "--provider", "deepseek",
    "--model", "deepseek-flash",
    "--base-url", "https://api.deepseek.com",
    "--max-iterations", "24",
    "--max-tool-calls", "80",
    "--budget-multiplier", "1",
    "--reasoning-effort", "high",
    "--solve-reasoning-effort", "high",
    "--model-timeout", "90",
    "--model-max-wall-time", "600",
    "--model-request-attempts", "5",
    "--model-parse-attempts", "3",
    "--temperature", "0.2",
    "--n-concurrent", "2",
    "--attempts", "1",
    "--max-retries", "0",
    "--agent-log-lines", "0",
)


def tmux_path() -> str:
    for candidate in TMUX_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("tmux")
    if found:
        return found
    raise RuntimeError("tmux is unavailable")


def paths(method: str) -> dict[str, Path | str]:
    job_name = f"{method}-tb2-paired30-20260922-01"
    work = ROOT / "runs" / method
    return {
        "job_name": job_name,
        "work": work,
        "job": work / "jobs" / job_name,
        "log": ROOT / "logs" / f"{method}.console.log",
        "socket": f"tb30-{method}",
        "session": f"terminal-{method}",
    }


def tmux_alive(method: str) -> bool:
    item = paths(method)
    completed = subprocess.run(
        [tmux_path(), "-L", str(item["socket"]), "has-session", "-t", str(item["session"])],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def status(method: str) -> dict[str, object]:
    item = paths(method)
    job = Path(item["job"])
    result_path = job / "result.json"
    result: dict[str, object] = {}
    if result_path.is_file():
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                result = loaded
        except (OSError, json.JSONDecodeError):
            pass
    stats = result.get("stats", {}) if isinstance(result, dict) else {}
    if not isinstance(stats, dict):
        stats = {}
    trials = [path for path in job.iterdir() if path.is_dir()] if job.is_dir() else []
    payload = {
        "method": method,
        "host": os.uname().nodename,
        "tmux_alive": tmux_alive(method),
        "job_dir": str(job),
        "trial_directories": len(trials),
        "result_exists": result_path.is_file(),
        "completed_trials": stats.get("n_completed_trials", 0),
        "errored_trials": stats.get("n_errored_trials", 0),
        "log": str(item["log"]),
    }
    return payload


def launch(method: str) -> dict[str, object]:
    if tmux_alive(method):
        raise RuntimeError(f"{method} tmux session is already alive")
    if not PYTHON.is_file() or not PROJECT.is_dir() or not SELECTION.is_file():
        raise RuntimeError("cloud runtime/project/selection is not prepared")
    credential = json.load(sys.stdin)
    deepseek_key = str(credential.get("deepseek_key", "")).strip()
    daytona_key = str(credential.get("daytona_key", "")).strip()
    if not deepseek_key or any(char.isspace() for char in deepseek_key):
        raise RuntimeError("invalid DeepSeek credential")
    if not daytona_key or any(char.isspace() for char in daytona_key):
        raise RuntimeError("invalid Daytona credential")

    item = paths(method)
    Path(item["work"]).mkdir(parents=True, exist_ok=True)
    Path(item["log"]).parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(PYTHON),
        str(PROJECT / COMMON[0]),
        "--method", method,
        "--job-name", str(item["job_name"]),
        "--workdir", str(item["work"]),
        *COMMON[1:],
    ]
    shell = (
        "cd " + shlex.quote(str(PROJECT)) + " && exec "
        + " ".join(shlex.quote(value) for value in command)
        + " >> " + shlex.quote(str(item["log"])) + " 2>&1"
    )
    env = os.environ.copy()
    env.update({
        "DEEPSEEK_API_KEY": deepseek_key,
        "DAYTONA_API_KEY": daytona_key,
        "PATH": str(PYTHON.parent) + os.pathsep + env.get("PATH", ""),
        "PYTHONPATH": str(PROJECT) + os.pathsep + str(PROJECT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    subprocess.run(
        [
            tmux_path(), "-L", str(item["socket"]), "new-session", "-d",
            "-s", str(item["session"]), "bash", "-lc", shell,
        ],
        env=env,
        check=True,
    )
    output = status(method)
    output["launched"] = True
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("launch", "status"))
    parser.add_argument("--method", choices=("bestfgs", "raw"), required=True)
    args = parser.parse_args()
    try:
        payload = launch(args.method) if args.action == "launch" else status(args.method)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
