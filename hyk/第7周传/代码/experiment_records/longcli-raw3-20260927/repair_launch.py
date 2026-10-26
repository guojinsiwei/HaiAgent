"""Narrow pre-run launch repair. No model calls or access to any credential."""
import hashlib
import json
import shlex
import sys
import time
from launch import HERE, PYTHON, tmux
from haiagent.storage import atomic_json

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if len(sys.argv) > 1 and sys.argv[1] == 'detached-probe':
    time.sleep(3)
    atomic_json(HERE/'tmux-detached-probe.json', {'detached_ok': True, 'model_calls': 0})
else:
    assert not (HERE/'health.json').exists() and not (HERE/'runs').exists(), 'Experiment already started'
    ready = json.loads((HERE/'ready.json').read_text())
    for name, expected in ready['hashes'].items():
        if name != 'launch.py':
            assert sha(HERE/name) == expected, name
    ready['hashes']['launch.py'] = sha(HERE/'launch.py')
    for p in (HERE/'tools/extracted').rglob('*'):
        if p.is_file() and not p.is_symlink():
            ready['hashes'][str(p.relative_to(HERE))] = sha(p)
    tmux('-V', check=True)
    command = f'exec {shlex.quote(PYTHON)} -B {shlex.quote(str(HERE/"repair_launch.py"))} detached-probe'
    tmux('-L','longcli-raw3-preflight','new-session','-d','-s','probe',command,check=True)
    atomic_json(HERE/'ready-before-launch-repair.json', json.loads((HERE/'ready.json').read_text()))
    atomic_json(HERE/'ready.json', ready)
    print('Started a zero-API detached probe; verify sentinel in a separate SSH connection.')
