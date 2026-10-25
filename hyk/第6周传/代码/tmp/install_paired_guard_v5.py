import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

BASE = Path('/mnt/lizh639/notebook-tools')
OUT = Path('/mnt/lizh639/bestfgs-runs/swe100-paired-v3')
TMUX = '/mnt/lizh639/envs/bestfgs/bin/tmux'
PYTHON = '/mnt/lizh639/envs/bestfgs/bin/python'


def main():
    data = json.load(sys.stdin)
    index = data['index']
    if os.uname().nodename != ['lizh639-aa91', 'lizh639-8e64'][index]:
        raise RuntimeError('Wrong host')
    env = dict(os.environ, DEEPSEEK_API_KEY=data['key'], PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MPLBACKEND='Agg')
    session, socket = f'guard-{index}', 'bestfgs-health-v3'
    if subprocess.run([TMUX, '-L', socket, 'has-session', '-t', session], capture_output=True).returncode == 0:
        print('GUARD_ALREADY_EXISTS', index)
        return
    if subprocess.run([TMUX, '-L', socket, 'list-sessions'], capture_output=True).returncode == 0:
        raise RuntimeError('Conflicting health tmux server')
    health = OUT / 'health'
    health.mkdir(parents=True, exist_ok=True)
    shell = shlex.join([PYTHON, str(BASE / 'paired_health_guard_v5.py'), str(index)]) + ' >> ' + shlex.quote(str(health / f'guard-{index}.log')) + ' 2>&1'
    subprocess.run([TMUX, '-L', socket, 'new-session', '-d', '-s', session, shell], env=env, capture_output=True, check=True)
    print('GUARD_STARTED', index)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('GUARD_SETUP_FAILED', type(exc).__name__)
        sys.exit(2)
