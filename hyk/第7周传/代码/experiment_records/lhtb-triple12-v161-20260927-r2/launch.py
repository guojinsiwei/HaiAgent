"""Hidden stdin credential -> authenticated, locked, detached experiment."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import time
import urllib.request
import urllib.error
from control import HERE, PYTHON, MODEL, validate


def main():
    with (HERE / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ready = validate()
        if (HERE / 'health.json').exists():
            raise RuntimeError('Already started; inspect status, do not replay')
        if subprocess.run(['tmux', '-L', 'lhtb-triple12', 'has-session', '-t', 'experiment'], capture_output=True).returncode == 0:
            raise RuntimeError('Worker already active')
        key = sys.stdin.readline().strip()
        if not key or any(c.isspace() for c in key):
            raise RuntimeError('Invalid credential')
        request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError('Authentication HTTP ' + str(error.code)) from None
        except Exception as error:
            raise RuntimeError('Authentication transport error: ' + type(error).__name__) from None
        if MODEL not in {m.get('id') for m in data.get('data', [])}:
            raise RuntimeError('Frozen model unavailable; no substitution')
        secret_dir = Path('/dev/shm') / ('lhtb12-' + secrets.token_hex(8))
        secret_dir.mkdir(mode=0o700)
        credential = secret_dir / 'api-key'
        fd = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(key)
        key = ''
        command = (f'cd {shlex.quote(str(HERE))} && exec {shlex.quote(PYTHON)} -B '
                   f'{shlex.quote(str(HERE / "control.py"))} run --credential {shlex.quote(str(credential))} '
                   f'>>{shlex.quote(str(HERE / "worker.log"))} 2>&1')
        try:
            subprocess.run(['tmux', '-L', 'lhtb-triple12', 'new-session', '-d', '-s', 'experiment', command], check=True)
        except Exception:
            credential.unlink(missing_ok=True)
            secret_dir.rmdir()
            raise
        for _ in range(20):
            if (HERE / 'health.json').exists():
                health = json.loads((HERE / 'health.json').read_text())
                print(json.dumps({'launched': health['state'] == 'running', 'state': health['state'],
                    'runs_total': 36, 'carried_forward': 4, 'new_attempts': 32, 'parallel_slots': 3, 'protocol_sha256': ready['protocol_sha256'],
                    'tmux_socket': 'lhtb-triple12', 'tmux_session': 'experiment'}))
                return
            time.sleep(.5)
        raise RuntimeError('Worker launch unconfirmed; inspect before retrying')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'launched': False, 'error': str(error)}))
        raise SystemExit(2)
