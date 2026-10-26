"""Read a new API key over encrypted stdin; no key in arguments or logs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

from common import ROOT, save
from runner import validate_ready


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    validate_ready()
    key = sys.stdin.readline().strip()
    assert key and not any(c.isspace() for c in key), 'Invalid credential'
    req = urllib.request.Request('https://api.deepseek.com/models',
        headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(req, timeout=30) as response:
        listing = json.load(response)
    assert any(m['id'] == 'deepseek-flash' for m in listing['data']), 'Required model unavailable'
    if args.check_only:
        print(json.dumps({'state': 'credential_preflight_passed', 'paid_model_calls': 0}))
        return
    claim = ROOT / 'launch.claim'
    descriptor = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    fd, name = tempfile.mkstemp(prefix='longcli-dsh20-', dir='/dev/shm')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(key)
        with (ROOT / 'worker.log').open('x') as log, (ROOT / 'worker-stderr.log').open('x') as errorlog:
            process = subprocess.Popen([sys.executable, '-B', str(ROOT / 'runner.py'), '--credential-file', name],
                stdout=log, stderr=errorlog, stdin=subprocess.DEVNULL, start_new_session=True, cwd=ROOT)
        save(ROOT / 'launch.json', {'pid': process.pid, 'state': 'starting', 'time': time.time(),
            'credential': 'new hidden input; consumed from 0600 tmpfs file then unlinked', 'concurrency': 4})
        time.sleep(2)
        assert process.poll() is None, 'Controller exited; inspect public worker status before retrying'
        print(json.dumps({'pid': process.pid, 'state': 'started', 'new_trials': 20, 'historical_dh_rerun': False}))
    except Exception:
        Path(name).unlink(missing_ok=True)
        # Retain the claim to prevent accidental duplicate spend after an uncertain launch.
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'state': 'launch_failed', 'error_type': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
