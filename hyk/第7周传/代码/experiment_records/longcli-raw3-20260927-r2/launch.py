"""Read hidden stdin key, authenticate read-only, launch once in detached tmux."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import urllib.request
from control import HERE, validate
from runner import PYTHON
from haiagent.model import NoRedirect

TMUX = str(HERE/'tools/extracted/usr/bin/tmux')
TMUX_ENV = dict(os.environ, LD_LIBRARY_PATH=str(HERE/'tools/extracted/usr/lib/x86_64-linux-gnu'))

def tmux(*args, **kwargs):
    return subprocess.run([TMUX, *args], env=TMUX_ENV, **kwargs)

def main():
    with (HERE/'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        protocol = validate()
        if (HERE/'health.json').exists() or (HERE/'runs').exists():
            raise RuntimeError('Already started; inspect status, never duplicate/restart automatically')
        tmux('-V', check=True, capture_output=True)
        if tmux('-L', 'longcli-raw3', 'has-session', '-t', 'raw3', capture_output=True).returncode == 0:
            raise RuntimeError('Worker already active')
        key = sys.stdin.readline().strip()
        if not key or any(c.isspace() for c in key):
            raise RuntimeError('Invalid credential')
        req = urllib.request.Request(protocol['endpoint']+'/models', headers={'Authorization': 'Bearer '+key})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
            models = json.load(response)
        if protocol['model'] not in {m.get('id') for m in models.get('data', [])}:
            raise RuntimeError('Frozen model unavailable; no substitution')
        folder = Path('/dev/shm')/('longcli-raw3-'+secrets.token_hex(8))
        folder.mkdir(mode=0o700)
        credential = folder/'api-key'
        fd = os.open(credential, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd,'w') as f:
            f.write(key)
        key = ''
        command = f'cd {shlex.quote(str(HERE))} && exec {PYTHON} -B control.py --credential {shlex.quote(str(credential))} >> worker.log 2>&1'
        try:
            tmux('-L','longcli-raw3','new-session','-d','-s','raw3',command,check=True)
        except Exception:
            credential.unlink(missing_ok=True)
            raise
        print(json.dumps({'launched': True, 'tasks': protocol['tasks'], 'model': protocol['model'],
                          'tmux_socket': 'longcli-raw3', 'tmux_session': 'raw3'}))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'launched': False, 'error_type': type(error).__name__,
                          'missing_file': getattr(error, 'filename', None) if isinstance(error, FileNotFoundError) else None,
                          'message': 'Launch failed; no credential values logged. Inspect readiness/authentication.'}))
        raise SystemExit(2)
