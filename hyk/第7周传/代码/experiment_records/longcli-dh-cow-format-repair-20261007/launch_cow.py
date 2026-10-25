"""Read one fresh key on stdin, verify it, then detach the isolated cow run."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parent


def validate():
    ready = json.loads((ROOT / "cow-ready.json").read_text())
    assert ready["ready"] and ready["paid_model_calls"] == 0
    for name, expected in ready["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    protocol = json.loads((ROOT / "protocol.json").read_text())
    assert [row["task"] for row in protocol["run_tasks"]] == ["61810_cow"]
    assert not (ROOT / "launch.claim").exists(), "Already launched"
    assert not (ROOT / "jobs/dh--61810_cow").exists(), "Task output exists"


def main():
    validate()
    if "--check" in sys.argv:
        print(json.dumps({"ready": True, "task": "61810_cow", "paid_model_calls": 0}))
        return
    key = sys.stdin.readline().strip()
    assert key and not any(char.isspace() for char in key)
    request = urllib.request.Request(
        "https://api.deepseek.com/models", headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(request, timeout=30) as response:
        models = json.load(response)
    assert any(model["id"] == "deepseek-flash" for model in models["data"])
    os.close(os.open(ROOT / "launch.claim", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    with (ROOT / "worker.log").open("x") as stdout, (ROOT / "worker-stderr.log").open("x") as stderr:
        child = subprocess.Popen([sys.executable, "-B", str(ROOT / "cow_worker.py")],
                                 cwd=ROOT, stdin=subprocess.PIPE, stdout=stdout,
                                 stderr=stderr, start_new_session=True, text=True)
        child.stdin.write(key + "\n")
        child.stdin.close()
    (ROOT / "launch.json").write_text(json.dumps({"pid": child.pid, "time": time.time(),
                                                   "task": "61810_cow", "attempt": "format-repair"}))
    print(json.dumps({"state": "started", "task": "61810_cow", "pid": child.pid}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"state": "launch_failed", "error_type": type(error).__name__}),
              file=sys.stderr)
        raise SystemExit(1)
