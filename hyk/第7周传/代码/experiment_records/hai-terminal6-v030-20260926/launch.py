"""Read a key from stdin, authenticate without logging it, detach locked worker."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import urllib.error
import urllib.request

from control import HERE, PYTHON, validate


def main():
    with (HERE / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        wrapped = validate()
        ready = json.loads((HERE / 'ready.json').read_text())
        if ready.get('protocol_sha256') != wrapped['sha256'] or not ready.get('ready'):
            raise RuntimeError('Offline preflight not ready')
        if subprocess.run(['tmux', '-L', 'hai-terminal6-v030', 'has-session', '-t', 'paired6'], capture_output=True).returncode == 0:
            raise RuntimeError('Worker already active; no duplicate launched')
        health = HERE / 'health.json'
        if health.exists():
            raise RuntimeError('Experiment was already started. Inspect health before any explicit resume')
        key = sys.stdin.readline().strip()
        if not key or any(c.isspace() for c in key):
            raise RuntimeError('Empty/invalid credential; nothing launched')
        request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'Authentication HTTP {error.code}; credential not logged') from None
        except Exception as error:
            raise RuntimeError(f'Authentication transport failure: {type(error).__name__}') from None
        if 'deepseek-flash' not in {m.get('id') for m in data.get('data', [])}:
            raise RuntimeError('Frozen model unavailable; no automatic substitution')
        secret_dir = Path('/dev/shm') / ('hai-tb6-' + secrets.token_hex(8))
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
            subprocess.run(['tmux', '-L', 'hai-terminal6-v030', 'new-session', '-d', '-s', 'paired6', command], check=True)
        except Exception:
            credential.unlink(missing_ok=True)
            secret_dir.rmdir()
            raise
        print(json.dumps({'launched': True, 'runs': 12, 'protocol_sha256': wrapped['sha256'],
                          'tmux_socket': 'hai-terminal6-v030', 'tmux_session': 'paired6'}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'launched': False, 'error': str(error)}))
        raise SystemExit(2)
