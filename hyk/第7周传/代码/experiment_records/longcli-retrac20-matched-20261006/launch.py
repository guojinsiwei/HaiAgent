"""New hidden input only. Consume a 0600 tmpfs handoff and unlink immediately."""
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
from check_ready import check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=int, required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    check(args.worker)
    claim = ROOT / f'launch-{args.worker}.claim'
    assert not claim.exists(), 'Already launched: never duplicate paid trials'
    key = sys.stdin.readline().strip()
    assert key and not any(c.isspace() for c in key)
    request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(request, timeout=30) as response:
        models = json.load(response)
    assert any(m['id'] == 'deepseek-flash' for m in models['data'])
    if args.check_only:
        print(json.dumps({'state': 'credential_preflight_passed', 'paid_model_calls': 0}))
        return
    os.close(os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    fd, filename = tempfile.mkstemp(prefix='longcli-retrac-', dir='/dev/shm')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(key)
        with (ROOT / f'worker-{args.worker}.log').open('x') as output, (ROOT / f'worker-{args.worker}-stderr.log').open('x') as error:
            process = subprocess.Popen([sys.executable, '-B', str(ROOT / 'runner.py'), '--worker', str(args.worker),
                                        '--credential-file', filename], stdout=output, stderr=error,
                                       stdin=subprocess.DEVNULL, start_new_session=True, cwd=ROOT,
                                       env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
        save(ROOT / f'launch-{args.worker}.json', {'state': 'starting', 'worker': args.worker, 'pid': process.pid,
                                  'time': time.time(), 'new_input_key': True, 'concurrency': 2})
        time.sleep(2)
        assert process.poll() is None, 'Worker exited; inspect public status before retrying'
        print(json.dumps({'state': 'queued_waiting_for_DSH', 'worker': args.worker, 'pid': process.pid}))
    except Exception:
        Path(filename).unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'state': 'launch_failed', 'error_type': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
