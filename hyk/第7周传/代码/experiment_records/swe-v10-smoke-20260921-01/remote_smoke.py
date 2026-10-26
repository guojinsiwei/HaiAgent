"""Bounded four-task deployment helper. Never prints or persists credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time
import urllib.request

CODE = Path('/mnt/lizh639/BestFGS-redundancy-v10-linux2')
ROOT = Path('/mnt/lizh639/bestfgs-runs/swe-v10-smoke-20260921-04')
PREPARED = Path('/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen')
PYTHON = '/mnt/lizh639/envs/bestfgs/bin/python'
TMUX = '/mnt/lizh639/envs/bestfgs/bin/tmux'
SOCKET = 'bestfgs-redundancy-v10-smoke04'
EXPECTED = '39982dace76e1a54e6db69f32eb9087609b7a18f642129af29362c3731a84f1f'
HOSTS = ['lizh639-aa91', 'lizh639-8e64']
IDS = [['django__django-15252', 'sympy__sympy-22080'],
       ['pytest-dev__pytest-10051', 'sphinx-doc__sphinx-7590']]
EXTRA = ['--provider', 'deepseek', '--model', 'deepseek-flash', '--base-url', 'https://api.deepseek.com',
         '--api-key-env', 'DEEPSEEK_API_KEY', '--temperature', '0.2', '--reasoning-effort', 'high',
         '--solve-reasoning-effort', 'high', '--max-iterations', '24', '--max-tool-calls', '80',
         '--max-commands-per-action', '6', '--budget-multiplier', '1', '--no-adaptive-budget',
         '--success-judge-mode', 'off', '--comparison-metrics', '--experience-mode', 'conditioned',
         '--model-timeout', '90', '--model-max-wall-time', '600', '--model-request-attempts', '5',
         '--model-parse-attempts', '3', '--model-retry-interval', '2', '--model-max-retry-interval', '30']


def dump(path, data, fresh=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh:
        with path.open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=True, indent=2)
    else:
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding='utf-8')
        tmp.replace(path)


def load_key():
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if key:
        return key, 'environment'
    # User requested configuring DeepSeek immediately before starting. Do not
    # recover old tmux credentials or inspect unrelated credential sources.
    return None, None


def runtime_env(key=None):
    env = dict(os.environ, PYTHONPATH=str(CODE / 'src'), PYTHONUNBUFFERED='1',
               PYTHONDONTWRITEBYTECODE='1', BESTFGS_TASK_SOURCE_PATH='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MPLBACKEND='Agg')
    env['PATH'] = str(Path(PYTHON).parent) + os.pathsep + env.get('PATH', '')
    if key:
        env['DEEPSEEK_API_KEY'] = key
    return env


def imports():
    sys.path[:0] = [str(CODE), str(CODE / 'src')]
    from benchmark_runtime import implementation_sha256
    if implementation_sha256(CODE) != EXPECTED:
        raise ValueError('Deployment implementation hash mismatch')


def prepare():
    imports()
    from benchmark_splits import reject_frozen_overlap
    from benchmark_runtime import canonical_sha256
    from run_notebook import load_tasks
    flattened = sum(IDS, [])
    reject_frozen_overlap(flattened, benchmark='swebench', allow_frozen_test_set=False)
    source_plan = json.loads((PREPARED / 'task-plan.json').read_text())
    allowed = {t['instance_id'] for t in source_plan['tasks']}
    if not set(flattened).issubset(allowed):
        raise ValueError('Selection must be in existing development cohort')
    if ROOT.exists():
        raise ValueError('Smoke output already exists; do not overwrite or retry silently')
    ROOT.mkdir()
    jobs = []
    for index, identities in enumerate(IDS):
        for identity in identities:
            directory = PREPARED / 'prepared' / identity
            ready = json.loads((directory / 'ready.json').read_text())
            manifest = ROOT / 'manifests' / (identity + '.json')
            dump(manifest, {'schema_version': 1, 'benchmark': 'swebench', 'tasks': [ready]}, fresh=True)
            output = ROOT / f'worker-{index}' / identity
            _, normalized = load_tasks(manifest, output)
            if normalized[0]['seed_sha256'] != ready['seed_sha256']:
                raise ValueError('Prepared seed differs from frozen preparation')
            jobs.append({'index': index, 'id': identity, 'manifest': str(manifest), 'output': str(output),
                         'workspace': ready['workspace'], 'task_python': ready['task_python'],
                         'seed_sha256': ready['seed_sha256'], 'prepared_commit': ready['prepared_commit'],
                         'pip_freeze_sha256': hashlib.sha256((directory / 'pip-freeze.txt').read_bytes()).hexdigest()})
    plan = {'schema_version': 1, 'implementation_sha256': EXPECTED, 'method': 'bestfgs', 'jobs': jobs,
            'hosts': HOSTS, 'agent_args': EXTRA, 'task_timeout': 14400, 'automatic_retries': 0,
            'launch_backend': {'kind': 'tmux', 'socket': SOCKET, 'one_worker_per_container': True},
            'selection': 'First development-cohort entry in each of django/sympy/pytest/sphinx; fixed before new outcomes.',
            'official_evaluation': False, 'metric_version': 'cli-comparison-v2', 'redundancy_version': 'reusable-evidence-v1'}
    dump(ROOT / 'smoke-plan.json', {'protocol': plan, 'protocol_sha256': canonical_sha256(plan)}, fresh=True)
    print(json.dumps({'prepared': True, 'ids': IDS, 'implementation_sha256': EXPECTED}))


def plan_for(index):
    imports()
    from benchmark_runtime import canonical_sha256
    data = json.loads((ROOT / 'smoke-plan.json').read_text())
    if canonical_sha256(data['protocol']) != data['protocol_sha256']:
        raise ValueError('Smoke protocol changed')
    if data['protocol']['implementation_sha256'] != EXPECTED or data['protocol']['agent_args'] != EXTRA:
        raise ValueError('Smoke implementation or budget changed')
    if os.uname().nodename != HOSTS[index]:
        raise ValueError('Wrong container for assigned worker')
    jobs = [j for j in data['protocol']['jobs'] if j['index'] == index]
    if [j['id'] for j in jobs] != IDS[index]:
        raise ValueError('Assigned task list changed')
    return data, jobs


def check_job(job):
    from run_comparison import check_prepared
    check_prepared(job, job)
    # Current interpreter and seeds are shared, never install or mutate packages.


def command(job, dry=False):
    return [PYTHON, str(CODE / 'run_notebook.py'), '--task-manifest', job['manifest'],
            '--output-root', job['output'], '--python', PYTHON, '--task-python', job['task_python'],
            '--task-timeout', '14400', *(['--dry-run'] if dry else []), '--', *EXTRA]


def preflight(index, auth=False):
    data, jobs = plan_for(index)
    key, source = load_key()
    env = runtime_env(key)
    for job in jobs:
        check_job(job)
        r = subprocess.run(command(job, dry=True), env=env, cwd=CODE, capture_output=True, text=True, timeout=180)
        if r.returncode:
            raise ValueError('Dry-run validation failed for ' + job['id'])
        record = json.loads(r.stdout)
        if record['implementation_sha256'] != EXPECTED or record['success_judge_mode'] != 'off':
            raise ValueError('Dry-run implementation or judge mismatch')
    auth_ok = None
    if auth and key:
        request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(request, timeout=30) as response:
            names = {x['id'] for x in json.load(response)['data']}
        if 'deepseek-flash' not in names:
            raise ValueError('Configured model unavailable')
        auth_ok = True
    summary = {'worker': index, 'host': HOSTS[index], 'ids': IDS[index], 'preflight_ok': True,
               'key_available': bool(key), 'credential_source': source, 'auth_ok': auth_ok,
               'protocol_sha256': data['protocol_sha256']}
    print(json.dumps(summary))
    return key, summary


def launch(index):
    key, summary = preflight(index, auth=True)
    if not key or summary['auth_ok'] is not True:
        raise ValueError('Missing usable DEEPSEEK_API_KEY; set it in server terminal')
    record = ROOT / f'worker-{index}.launch.json'
    session = f'worker-{index}'
    if subprocess.run([TMUX, '-L', SOCKET, 'has-session', '-t', session],
                      capture_output=True, timeout=10).returncode == 0:
        raise ValueError('Dedicated tmux session already exists; inspect status instead of duplicating it')
    # Exclusive launch claim: no second launch, including after a failed run.
    dump(record, {'state': 'launching', **summary}, fresh=True)
    log = ROOT / f'worker-{index}.console.log'
    log.open('xb').close()
    worker_command = [PYTHON, str(Path(__file__).resolve()), 'worker', '--index', str(index)]
    shell_command = shlex.join(worker_command) + ' >> ' + shlex.quote(str(log)) + ' 2>&1'
    created = subprocess.run([TMUX, '-L', SOCKET, 'new-session', '-d', '-P', '-F', '#{pid}',
                              '-s', session, '-c', str(CODE), shell_command],
                             env=runtime_env(key), capture_output=True, text=True, check=True, timeout=30)
    server_pid = int(created.stdout.strip())
    if subprocess.run([TMUX, '-L', SOCKET, 'has-session', '-t', session],
                      capture_output=True, timeout=10).returncode:
        raise RuntimeError('tmux session did not remain alive after launch')
    dump(record, {'state': 'launched', 'tmux_server_pid': server_pid, 'tmux_socket': SOCKET,
                  'tmux_session': session, 'log': str(log), **summary})
    print(json.dumps({'launched': True, 'tmux_socket': SOCKET, 'tmux_session': session,
                      'worker': index, 'log': str(log)}))


def worker(index):
    data, jobs = plan_for(index)
    state = {'pid': os.getpid(), 'host': HOSTS[index], 'worker': index, 'status': 'starting',
             'protocol_sha256': data['protocol_sha256'], 'jobs_completed': [], 'automatic_retries': 0}
    stop = threading.Event()
    lock = threading.Lock()
    def heartbeat():
        while not stop.is_set():
            with lock:
                dump(ROOT / f'worker-{index}.health.json', {**state, 'heartbeat_unix': time.time()})
            stop.wait(20)
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        for job in jobs:
            imports()
            check_job(job)
            with lock:
                state.update(status='running', task_id=job['id'], started_unix=time.time())
            process = subprocess.Popen(command(job), cwd=CODE, env=runtime_env(), stdin=subprocess.DEVNULL)
            with lock:
                state['runner_pid'] = process.pid
            code = process.wait()
            check_job(job)
            item = {'id': job['id'], 'exit_code': code, 'ended_unix': time.time()}
            with lock:
                state['jobs_completed'].append(item)
                state['runner_pid'] = None
            # Do not automatically repeat failures or keep spending after an
            # infrastructure error. Algorithmic failures normally exit runner 0.
            if code:
                with lock:
                    state['status'] = 'needs_attention'
                break
        else:
            with lock:
                state['status'] = 'completed'
    except Exception as error:
        with lock:
            state.update(status='needs_attention', error_type=type(error).__name__)
    finally:
        stop.set()
        thread.join(timeout=10)
        dump(ROOT / f'worker-{index}.health.json', {**state, 'heartbeat_unix': time.time()})


def status(index):
    data, jobs = plan_for(index)
    health = ROOT / f'worker-{index}.health.json'
    state = json.loads(health.read_text()) if health.exists() else {'status': 'not_started'}
    state['heartbeat_age_seconds'] = round(time.time() - state.get('heartbeat_unix', time.time()), 1)
    state['process_alive'] = Path('/proc/' + str(state.get('pid', -1))).exists()
    state['tmux_socket'] = SOCKET
    state['tmux_session'] = f'worker-{index}'
    state['tmux_session_alive'] = subprocess.run(
        [TMUX, '-L', SOCKET, 'has-session', '-t', state['tmux_session']],
        capture_output=True, timeout=10).returncode == 0
    state['tasks'] = []
    for job in jobs:
        path = Path(job['output']) / job['id'] / 'status.json'
        record = json.loads(path.read_text()) if path.exists() else {}
        item = {k: record.get(k) for k in ('status', 'stop_reason', 'exit_code', 'submitted', 'local_validation_passed')}
        item['id'] = job['id']
        if record.get('attempt'):
            attempt = Path(record['attempt'])
            log = attempt / 'agent.log'
            if log.exists():
                text = log.read_text(errors='replace')
                item.update(log_bytes=log.stat().st_size, log_age_seconds=round(time.time() - log.stat().st_mtime, 1),
                    api_responses=text.count('模型响应已收到'), api_requests=text.count('正在请求'),
                    cli_completions=text.count('命令结束：'), api_401=('状态码=401' in text),
                    api_402=('状态码=402' in text))
            trace = attempt / 'snapshots' / 'cli-metrics.jsonl'
            if trace.exists():
                from bestfgs.experiment_metrics import summarize_trace
                m = summarize_trace(trace)
                item['metrics'] = {k: m.get(k) for k in ('tool_calls', 'interaction_rounds', 'redundant_tool_calls',
                    'redundancy_unknown_calls', 'tool_call_redundancy_rate', 'metric_version', 'trace_complete')}
        state['tasks'].append(item)
    print(json.dumps(state))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['inspect', 'prepare', 'preflight', 'launch', 'worker', 'status'])
    parser.add_argument('--index', type=int, choices=[0, 1], default=0)
    parser.add_argument('--credential-stdin', action='store_true')
    args = parser.parse_args()
    try:
        if args.credential_stdin:
            if args.action != 'launch':
                raise ValueError('Credential input is only accepted at explicit launch')
            payload = json.load(sys.stdin)
            key = payload.get('key', '').strip()
            if not key or any(c.isspace() for c in key):
                raise ValueError('Invalid credential format')
            os.environ['DEEPSEEK_API_KEY'] = key
        if args.action == 'inspect':
            key, source = load_key()
            print(json.dumps({'host': os.uname().nodename, 'key_available': bool(key), 'credential_source': source}))
        elif args.action == 'prepare':
            prepare()
        elif args.action == 'preflight':
            preflight(args.index, auth=False)
        else:
            globals()[args.action](args.index)
    except Exception as error:
        # Never print request exception content, environments or key values.
        print(json.dumps({'error_type': type(error).__name__, 'stage': args.action,
                          'message': str(error) if isinstance(error, ValueError) else 'Operation failed; no credentials logged'}))
        sys.exit(2)
