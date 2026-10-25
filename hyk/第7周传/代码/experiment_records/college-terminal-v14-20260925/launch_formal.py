"""Validate a key without logging it, then launch the frozen worker in detached tmux."""
from pathlib import Path
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE / "experiment"
key = sys.stdin.readline().strip()
if not key or any(ch.isspace() for ch in key):
    raise SystemExit("Missing or malformed key; nothing started")
request = urllib.request.Request("https://api.deepseek.com/models", headers={"Authorization": "Bearer " + key})
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        models = json.load(response)
except urllib.error.HTTPError as error:
    raise SystemExit(f"Authentication check HTTP {error.code}; nothing started") from None
if "deepseek-flash" not in {item.get("id") for item in models.get("data", [])}:
    raise SystemExit("Frozen model deepseek-flash is unavailable; refusing substitution")

subprocess.run([str(HERE / "runtime/bin/python"), str(HERE / "paired_control.py"), "validate"], check=True)
if subprocess.run(["tmux", "-L", "tb-v14", "has-session", "-t", "paired36"], capture_output=True).returncode == 0:
    raise SystemExit("Worker is already active; refusing duplicate")
credential_dir = Path("/dev/shm") / ("tb-v14-" + secrets.token_hex(8))
credential_dir.mkdir(mode=0o700)
credential = credential_dir / "deepseek_api_key"
fd = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(key)
key = ""
command = (
    f"cd {HERE} && export CREDENTIALS_DIRECTORY={credential_dir} PYTHONUNBUFFERED=1 HARBOR_TELEMETRY=0; "
    f"exec {HERE / 'runtime/bin/python'} {HERE / 'paired_control.py'} run "
    f">>{ROOT / 'worker.console.log'} 2>&1"
)
try:
    subprocess.run(["tmux", "-L", "tb-v14", "new-session", "-d", "-s", "paired36", command], check=True)
except Exception:
    credential.unlink(missing_ok=True)
    credential_dir.rmdir()
    raise
print(json.dumps({"launched": True, "session": "paired36", "socket": "tb-v14",
                  "protocol": json.loads((ROOT / "control/protocol.json").read_text())["protocol_sha256"]}))
