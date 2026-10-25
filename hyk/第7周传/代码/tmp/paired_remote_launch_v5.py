"""Read credentials only from stdin, never write them into logs or files."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import urllib.request
import urllib.error

ROOT = Path('/mnt/lizh639/BestFGS-compare-v5')
OUTPUT = Path('/mnt/lizh639/bestfgs-runs/swe100-paired-v3')
PREPARED = Path('/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen')
PYTHON = '/mnt/lizh639/envs/bestfgs/bin/python'
TMUX = '/mnt/lizh639/envs/bestfgs/bin/tmux'
SOCKET = 'bestfgs-paired-v3'


def main():
    data = json.load(sys.stdin)
    index = data['index']
    expected_host = ['lizh639-aa91', 'lizh639-8e64'][index]
    if os.uname().nodename != expected_host:
        raise RuntimeError('Wrong notebook')
    key = data['key'].strip()
    if not key or any(c.isspace() for c in key):
        raise RuntimeError('Invalid credential format')
    command = [PYTHON, str(ROOT / 'run_comparison.py'), 'plan', '--plan', str(PREPARED / 'task-plan.json'),
               '--prepared-root', str(PREPARED), '--output-root', str(OUTPUT), '--shard-count', '2',
               '--shard-index', str(index)]
    env = dict(os.environ, DEEPSEEK_API_KEY=key, PYTHONPATH=str(ROOT / 'src'),
               PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MPLBACKEND='Agg')
    plan_result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
    if plan_result.returncode:
        raise RuntimeError('Plan validation failed')
    plan = json.loads(plan_result.stdout)
    if plan['total'] != 100 or plan['ready'] != 100 or len(plan['assigned_ids']) != 50:
        raise RuntimeError('Expected 100 ready tasks and 50 assigned tasks')
    if plan['plan_sha256'] != '8e46676a0b79150c84a9fca745bed3638dd1f4f6e8bad6df4ca62405609affe7':
        raise RuntimeError('Frozen plan changed')
    if data['action'] == 'preflight':
        request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(request, timeout=30) as response:
            models = [row['id'] for row in json.load(response)['data']]
        if 'deepseek-flash' not in models:
            raise RuntimeError('Configured model unavailable')
        print(json.dumps({'index': index, 'host': expected_host, 'auth': 200,
                          'protocol_sha256': plan['protocol_sha256'], 'assigned_ids': plan['assigned_ids']}))
        return
    if data['action'] != 'start' or plan['protocol_sha256'] != data['protocol_sha256']:
        raise RuntimeError('Protocol mismatch before launch')
    if subprocess.run([TMUX, '-L', SOCKET, 'list-sessions'], capture_output=True).returncode == 0:
        raise RuntimeError('Dedicated tmux server already exists; inspect before retry')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    command[2] = 'run'
    logfile = OUTPUT / f'worker-{index}.console.log'
    if logfile.exists():
        raise RuntimeError('Existing console log; inspect before retry')
    shell_command = 'cd ' + shlex.quote(str(ROOT)) + ' && ' + shlex.join(command) + ' > ' + shlex.quote(str(logfile)) + ' 2>&1'
    subprocess.run([TMUX, '-L', SOCKET, 'new-session', '-d', '-s', f'worker-{index}', shell_command],
                   env=env, check=True, capture_output=True, timeout=30)
    print(json.dumps({'started': True, 'index': index, 'host': expected_host, 'log': str(logfile)}))


try:
    main()
except urllib.error.HTTPError as error:
    print(json.dumps({'error': 'API authentication request rejected', 'status': error.code}))
    sys.exit(2)
except Exception as error:
    # Deliberately never print exception payloads, request headers or credentials.
    print(json.dumps({'error': type(error).__name__, 'stage': 'preflight_or_launch'}))
    sys.exit(2)
