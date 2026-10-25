"""Read hidden stdin key, authenticate read-only, launch once in detached tmux."""
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
from control import HERE, validate
from runner import PYTHON
from haiagent.model import NoRedirect
from net_transport import request as network_request

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
        for attempt in range(4):
            kind,body=network_request(protocol['endpoint']+'/models',None,key,30)
            if kind=='ok': break
            if kind=='http' and body not in {408,429,500,502,503,504}: break
            if attempt<3: time.sleep(3)
        if kind!='ok': raise RuntimeError('Authentication/transport unavailable: '+str(body))
        models=json.loads(body)
        if protocol['model'] not in {m.get('id') for m in models.get('data', [])}:
            raise RuntimeError('Frozen model unavailable; no substitution')
        folder = Path('/dev/shm')/('longcli-raw3-'+secrets.token_hex(8))
        folder.mkdir(mode=0o700)
        credential = folder/'api-key'
        fd = os.open(credential, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd,'w') as f:
            f.write(key)
        key = ''
        command = f'cd {shlex.quote(str(HERE))} && exec {PYTHON} -B supervise.py guard {shlex.quote(str(credential))} >> worker.log 2>&1'
        try:
            tmux('-L','longcli-raw3','new-session','-d','-s','raw3',command,check=True)
        except Exception:
            credential.unlink(missing_ok=True)
            raise
        for _ in range(30):
            if (HERE/'health.json').exists():
                health=json.loads((HERE/'health.json').read_text())
                print(json.dumps({'launched':health['state']=='running','state':health['state'],
                    'tasks':protocol['tasks'],'model':protocol['model'],
                    'tmux_socket':'longcli-raw3','tmux_session':'raw3'}))
                return
            time.sleep(.5)
        raise RuntimeError('No worker heartbeat; inspect before retry')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'launched': False, 'error_type': type(error).__name__,
                          'missing_file': getattr(error, 'filename', None) if isinstance(error, FileNotFoundError) else None,
                          'message': 'Launch failed; no credential values logged. Inspect readiness/authentication.'}))
        raise SystemExit(2)
