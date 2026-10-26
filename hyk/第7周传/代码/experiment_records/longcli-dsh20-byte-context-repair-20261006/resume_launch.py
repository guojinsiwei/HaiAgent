"""Fresh encrypted-stdin key, tmpfs handoff, one recovery launch only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from common import ROOT, save
from resume_worker import preflight


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    health = preflight()
    if args.check_only:
        print(json.dumps({'state': 'resume_ready', 'pending': health['pending'], 'paid_api_calls': 0}))
        return
    key = sys.stdin.readline().strip()
    assert key and not any(c.isspace() for c in key)
    request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(request, timeout=30) as response:
        models = json.load(response)
    assert any(m['id'] == 'deepseek-flash' for m in models['data'])
    os.close(os.open(ROOT / 'resume-four.claim', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    fd, filename = tempfile.mkstemp(prefix='longcli-dsh-resume-', dir='/dev/shm')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(key)
        with (ROOT / 'worker-0-resume.log').open('x') as out, (ROOT / 'worker-0-resume-stderr.log').open('x') as err:
            process = subprocess.Popen([sys.executable, '-B', str(ROOT / 'resume_worker.py'),
                                        '--credential-file', filename], stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True, cwd=ROOT)
        save(ROOT / 'resume-launch.json', {'pid': process.pid, 'time': time.time(),
                                          'tasks': health['pending'], 'concurrency': 2})
        time.sleep(2)
        assert process.poll() is None, 'Resume exited; inspect public status, never duplicate'
        print(json.dumps({'state': 'started', 'pid': process.pid, 'tasks': health['pending']}))
    except Exception:
        Path(filename).unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'state': 'resume_failed', 'error_type': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
