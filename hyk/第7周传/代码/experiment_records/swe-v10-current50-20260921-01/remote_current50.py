"""Frozen 50-task current-BestFGS run with two-container atomic scheduling.

Credentials are accepted only at explicit launch via stdin. Tasks are never
automatically retried. Atomic mkdir claims ensure one actual run per task.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time
import urllib.request

CODE = Path('/mnt/lizh639/BestFGS-redundancy-v10-linux2')
ROOT = Path('/mnt/lizh639/bestfgs-runs/swe-v10-current50-20260921-01')
PREPARED = Path('/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen')
PYTHON = '/mnt/lizh639/envs/bestfgs/bin/python'
TMUX = '/mnt/lizh639/envs/bestfgs/bin/tmux'
SOCKET = 'bestfgs-redundancy-v10-current50-01'
EXPECTED_IMPLEMENTATION = '39982dace76e1a54e6db69f32eb9087609b7a18f642129af29362c3731a84f1f'
HOSTS = ('lizh639-aa91', 'lizh639-8e64')
SELECTION_SEED = 20260921
COUNT = 50
SMOKE_IDS = {'django__django-15252', 'sympy__sympy-22080',
             'pytest-dev__pytest-10051', 'sphinx-doc__sphinx-7590'}
EXTRA = ['--provider', 'deepseek', '--model', 'deepseek-flash', '--base-url', 'https://api.deepseek.com',
         '--api-key-env', 'DEEPSEEK_API_KEY', '--temperature', '0.2', '--reasoning-effort', 'high',
         '--solve-reasoning-effort', 'high', '--max-iterations', '24', '--max-tool-calls', '80',
         '--max-commands-per-action', '6', '--budget-multiplier', '1', '--no-adaptive-budget',
         '--success-judge-mode', 'off', '--comparison-metrics', '--experience-mode', 'conditioned',
         '--model-timeout', '90', '--model-max-wall-time', '600', '--model-request-attempts', '5',
         '--model-parse-attempts', '3', '--model-retry-interval', '2', '--model-max-retry-interval', '30']


def atomic_json(path: Path, value, *, fresh=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
        return
    temporary = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding='utf-8')
    temporary.replace(path)


def runtime_env(key=None):
    environment = dict(os.environ, PYTHONPATH=str(CODE / 'src'), PYTHONUNBUFFERED='1',
        PYTHONDONTWRITEBYTECODE='1', BESTFGS_TASK_SOURCE_PATH='1', OMP_NUM_THREADS='1',
        OPENBLAS_NUM_THREADS='1', MPLBACKEND='Agg')
    environment['PATH'] = str(Path(PYTHON).parent) + os.pathsep + environment.get('PATH', '')
    if key:
        environment['DEEPSEEK_API_KEY'] = key
    return environment


def imports():
    sys.path[:0] = [str(CODE), str(CODE / 'src')]
    from benchmark_runtime import implementation_sha256
    if implementation_sha256(CODE) != EXPECTED_IMPLEMENTATION:
        raise ValueError('Implementation hash mismatch')


def ranking(identity):
    return hashlib.sha256(f'{SELECTION_SEED}\0{identity}'.encode()).hexdigest()


def prepare():
    imports()
    from benchmark_runtime import canonical_sha256
    from benchmark_splits import reject_frozen_overlap
    if ROOT.exists():
        raise ValueError('Output root already exists; never overwrite a frozen experiment')
    source = json.loads((PREPARED / 'task-plan.json').read_text(encoding='utf-8'))
    tasks = {task['instance_id']: task for task in source['tasks']}
    eligible = sorted(set(tasks) - SMOKE_IDS, key=lambda identity: (ranking(identity), identity))
    if len(eligible) < COUNT:
        raise ValueError('Not enough prepared non-smoke development tasks')
    selected = eligible[:COUNT]
    reject_frozen_overlap(selected, benchmark='swebench', allow_frozen_test_set=False)
    ROOT.mkdir()
    # Create shared coordination parents before either worker can launch.  A
    # claim itself is then one single-directory mkdir, which is atomic on the
    # shared filesystem and cannot be weakened by concurrent parent creation.
    (ROOT / 'claims').mkdir()
    (ROOT / 'outcomes').mkdir()
    jobs = []
    for position, identity in enumerate(selected):
        recipe = tasks[identity]
        directory = PREPARED / 'prepared' / identity
        ready_path, freeze_path = directory / 'ready.json', directory / 'pip-freeze.txt'
        if not ready_path.is_file() or not freeze_path.is_file():
            raise ValueError('Prepared task is incomplete: ' + identity)
        ready = json.loads(ready_path.read_text(encoding='utf-8'))
        if (ready.get('id') != identity or ready.get('base_commit') != recipe.get('base_commit')
                or ready.get('recipe_sha256') != canonical_sha256(recipe)
                or ready.get('goal') != recipe.get('problem_statement')):
            raise ValueError('Prepared recipe mismatch: ' + identity)
        manifest = ROOT / 'manifests' / (identity + '.json')
        atomic_json(manifest, {'schema_version': 1, 'benchmark': 'swebench', 'tasks': [ready]}, fresh=True)
        jobs.append({'id': identity, 'position': position, 'preferred_worker': position % 2,
            'manifest': str(manifest), 'output': str(ROOT / 'tasks' / identity),
            'workspace': ready['workspace'], 'task_python': ready['task_python'],
            'seed_sha256': ready['seed_sha256'], 'prepared_commit': ready['prepared_commit'],
            'pip_freeze_sha256': hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
            'repository': identity.split('__', 1)[0]})
    protocol = {'schema_version': 1, 'name': 'swe-v10-current50-20260921-01',
        'implementation_sha256': EXPECTED_IMPLEMENTATION, 'metric_version': 'cli-comparison-v2',
        'metric_report_version': 'cli-metrics-report-v3', 'redundancy_version': 'reusable-evidence-v1',
        'method': 'bestfgs-conditioned-current-only', 'dataset': source['dataset'], 'split': source['split'],
        'selection': {'source_plan_sha256': source['plan_sha256'], 'seed': SELECTION_SEED,
                      'rule': 'SHA256(seed + NUL + instance_id), first 50 after excluding four smoke tasks',
                      'excluded_smoke_ids': sorted(SMOKE_IDS), 'ids': selected},
        'agent_args': EXTRA, 'task_timeout_seconds': 14400, 'official_evaluation': False,
        'automatic_task_retries': 0, 'hosts': list(HOSTS),
        'scheduler': {'version': 'atomic-mkdir-v1', 'preferred_static_shards': 'position modulo 2',
                      'work_stealing': 'after preferred tasks are all claimed; unclaimed tasks only',
                      'claim_atomicity': 'shared-filesystem mkdir',
                      'claimed_task_recovery': 'never automatic; needs explicit audit',
                      'one_active_task_per_worker': True, 'tmux_socket': SOCKET},
        'jobs': jobs}
    atomic_json(ROOT / 'experiment-plan.json',
                {'protocol': protocol, 'protocol_sha256': canonical_sha256(protocol)}, fresh=True)
    distribution = {str(worker): dict(Counter(job['repository'] for job in jobs
                                               if job['preferred_worker'] == worker)) for worker in (0, 1)}
    print(json.dumps({'prepared': True, 'N': len(jobs), 'preferred_counts': [25, 25],
                      'repository_distribution': distribution,
                      'protocol_sha256': canonical_sha256(protocol),
                      'implementation_sha256': EXPECTED_IMPLEMENTATION}))


def load_plan(index):
    imports()
    from benchmark_runtime import canonical_sha256
    document = json.loads((ROOT / 'experiment-plan.json').read_text(encoding='utf-8'))
    protocol = document['protocol']
    if canonical_sha256(protocol) != document['protocol_sha256']:
        raise ValueError('Experiment protocol checksum mismatch')
    if (protocol['implementation_sha256'] != EXPECTED_IMPLEMENTATION or protocol['agent_args'] != EXTRA
            or len(protocol['jobs']) != COUNT or len(set(protocol['selection']['ids'])) != COUNT):
        raise ValueError('Frozen code, arguments or task denominator changed')
    if os.uname().nodename != HOSTS[index]:
        raise ValueError('Wrong worker/container assignment')
    return document


def check_ready(job):
    from run_comparison import check_prepared
    check_prepared(job, job)


def task_command(job, dry=False):
    return [PYTHON, str(CODE / 'run_notebook.py'), '--task-manifest', job['manifest'],
        '--output-root', job['output'], '--python', PYTHON, '--task-python', job['task_python'],
        '--task-timeout', '14400', *(['--dry-run'] if dry else []), '--', *EXTRA]


def smoke_still_active():
    result = subprocess.run(['pgrep', '-f', 'run_notebook.py.*swe-v10-smoke-20260921-04'],
                            capture_output=True, text=True, timeout=10)
    return result.returncode == 0 and bool(result.stdout.strip())


def preflight(index, *, key=None, authenticate=False):
    document = load_plan(index)
    protocol = document['protocol']
    own = [job for job in protocol['jobs'] if job['preferred_worker'] == index]
    # Full seed/freeze checks happen immediately before each claim is executed,
    # distributed across containers. Here validate every immutable manifest and
    # perform a complete agent argument parse without hashing all 50 repos twice.
    for job in protocol['jobs']:
        manifest = json.loads(Path(job['manifest']).read_text(encoding='utf-8'))
        if manifest.get('benchmark') != 'swebench' or manifest['tasks'][0].get('id') != job['id']:
            raise ValueError('Manifest mismatch: ' + job['id'])
    probe = subprocess.run(task_command(own[0], dry=True), cwd=CODE, env=runtime_env(key),
                           capture_output=True, text=True, timeout=180)
    if probe.returncode:
        raise ValueError('Agent dry-run preflight failed')
    parsed = json.loads(probe.stdout)
    if parsed.get('implementation_sha256') != EXPECTED_IMPLEMENTATION or parsed.get('success_judge_mode') != 'off':
        raise ValueError('Agent dry-run does not match frozen protocol')
    auth = None
    if authenticate:
        if not key:
            raise ValueError('Missing API key')
        request = urllib.request.Request('https://api.deepseek.com/models',
                                         headers={'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(request, timeout=30) as response:
            names = {row['id'] for row in json.load(response)['data']}
        if 'deepseek-flash' not in names:
            raise ValueError('Configured model is unavailable')
        auth = True
    result = {'worker': index, 'host': HOSTS[index], 'N': COUNT, 'preferred_tasks': len(own),
              'preflight_ok': True, 'auth_ok': auth,
              'smoke_still_active': smoke_still_active(),
              'protocol_sha256': document['protocol_sha256']}
    print(json.dumps(result))
    return result


def launch(index, key):
    summary = preflight(index, key=key, authenticate=True)
    if summary['smoke_still_active']:
        raise ValueError('Smoke task still active on this container; wait before large-run launch')
    session = f'worker-{index}'
    if subprocess.run([TMUX, '-L', SOCKET, 'has-session', '-t', session],
                      capture_output=True, timeout=10).returncode == 0:
        raise ValueError('Dedicated tmux session already exists')
    launch_record = ROOT / f'worker-{index}.launch.json'
    atomic_json(launch_record, {'state': 'launching', **summary}, fresh=True)
    log = ROOT / f'worker-{index}.console.log'
    log.open('xb').close()
    command = [PYTHON, str(Path(__file__).resolve()), 'worker', '--index', str(index)]
    shell_command = shlex.join(command) + ' >> ' + shlex.quote(str(log)) + ' 2>&1'
    created = subprocess.run([TMUX, '-L', SOCKET, 'new-session', '-d', '-P', '-F', '#{pid}',
                              '-s', session, '-c', str(CODE), shell_command],
                             env=runtime_env(key), capture_output=True, text=True, check=True, timeout=30)
    if subprocess.run([TMUX, '-L', SOCKET, 'has-session', '-t', session],
                      capture_output=True, timeout=10).returncode:
        raise RuntimeError('tmux worker did not remain alive')
    atomic_json(launch_record, {'state': 'launched', 'tmux_server_pid': int(created.stdout.strip()),
        'tmux_socket': SOCKET, 'tmux_session': session, 'log': str(log), **summary})
    print(json.dumps({'launched': True, 'worker': index, 'tmux_socket': SOCKET,
                      'tmux_session': session, 'log': str(log)}))


def claim(job, index):
    directory = ROOT / 'claims' / job['id']
    try:
        directory.mkdir(exist_ok=False)
    except FileExistsError:
        return False
    atomic_json(directory / 'claim.json', {'id': job['id'], 'worker': index, 'host': HOSTS[index],
        'pid': os.getpid(), 'claimed_unix': time.time(), 'protocol_sha256':
        json.loads((ROOT / 'experiment-plan.json').read_text())['protocol_sha256']}, fresh=True)
    return True


def read_task_state(job):
    path = Path(job['output']) / job['id'] / 'status.json'
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'status': 'artifact_error'}


def systemic_failure(job):
    state = read_task_state(job)
    reason = str(state.get('error', '')) + ' ' + str(state.get('stop_reason', ''))
    attempt_value = state.get('attempt')
    log = Path(attempt_value) / 'agent.log' if attempt_value else None
    if log is not None and log.is_file():
        # Bounded tail; never report the content, only match public error classes.
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 256_000))
            reason += ' ' + stream.read().decode('utf-8', errors='replace')
    lowered = reason.casefold()
    return any(marker in lowered for marker in
               ('状态码=401', '状态码=402', 'authentication fails', 'invalid api key',
                'insufficient balance', 'insufficient_balance', '余额不足'))


def worker(index):
    document = load_plan(index)
    jobs = document['protocol']['jobs']
    preferred = [job for job in jobs if job['preferred_worker'] == index]
    steal = [job for job in jobs if job['preferred_worker'] != index]
    state = {'worker': index, 'host': HOSTS[index], 'pid': os.getpid(), 'status': 'starting',
        'protocol_sha256': document['protocol_sha256'], 'current_task': None,
        'completed_by_worker': 0, 'errors_by_worker': 0, 'automatic_retries': 0}
    lock, stop = threading.Lock(), threading.Event()
    def heartbeat():
        while not stop.is_set():
            with lock:
                atomic_json(ROOT / f'worker-{index}.health.json', {**state, 'heartbeat_unix': time.time()})
            stop.wait(20)
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        for phase, queue in (('preferred', preferred), ('steal', steal)):
            for job in queue:
                if (ROOT / 'outcomes' / (job['id'] + '.json')).exists() or not claim(job, index):
                    continue
                with lock:
                    state.update(status='running', scheduling_phase=phase, current_task=job['id'],
                                 current_started_unix=time.time())
                try:
                    imports()
                    check_ready(job)
                except Exception as error:
                    atomic_json(ROOT / 'outcomes' / (job['id'] + '.json'),
                        {'id': job['id'], 'worker': index, 'status': 'preflight_error',
                         'error_type': type(error).__name__, 'ended_unix': time.time()}, fresh=True)
                    with lock:
                        state.update(status='needs_attention', error_type=type(error).__name__)
                        state['errors_by_worker'] += 1
                    return
                process = subprocess.Popen(task_command(job), cwd=CODE, env=runtime_env(),
                                           stdin=subprocess.DEVNULL)
                with lock:
                    state['runner_pid'] = process.pid
                code = process.wait()
                try:
                    check_ready(job)
                    seed_ok = True
                except Exception:
                    seed_ok = False
                task_state = read_task_state(job)
                outcome = {'id': job['id'], 'worker': index, 'preferred_worker': job['preferred_worker'],
                    'scheduling_phase': phase, 'exit_code': code, 'seed_ok_after': seed_ok,
                    'task_status': task_state.get('status'), 'stop_reason': task_state.get('stop_reason'),
                    'ended_unix': time.time(), 'automatic_retry': False}
                atomic_json(ROOT / 'outcomes' / (job['id'] + '.json'), outcome, fresh=True)
                with lock:
                    state['runner_pid'] = None
                    state['current_task'] = None
                    state['completed_by_worker'] += 1
                    state['errors_by_worker'] += int(code != 0 or not seed_ok)
                if not seed_ok or systemic_failure(job):
                    with lock:
                        state['status'] = 'needs_attention'
                        state['systemic_stop'] = True
                    return
        # A faster worker may reach here while the peer still owns active claims.
        # Wait without re-running or stealing claimed work.
        while True:
            outcomes = list((ROOT / 'outcomes').glob('*.json')) if (ROOT / 'outcomes').is_dir() else []
            if len(outcomes) == COUNT:
                with lock:
                    state['status'] = 'completed'
                return
            peer_path = ROOT / f'worker-{1-index}.health.json'
            peer = json.loads(peer_path.read_text()) if peer_path.is_file() else {}
            age = time.time() - peer.get('heartbeat_unix', 0)
            if peer and age > 180 and peer.get('status') not in {'completed'}:
                with lock:
                    state.update(status='needs_attention', peer_heartbeat_stale=True)
                return
            with lock:
                state.update(status='waiting_for_peer', remaining_outcomes=COUNT-len(outcomes))
            time.sleep(30)
    finally:
        stop.set()
        thread.join(timeout=10)
        atomic_json(ROOT / f'worker-{index}.health.json', {**state, 'heartbeat_unix': time.time()})


def status(index=None):
    document = json.loads((ROOT / 'experiment-plan.json').read_text(encoding='utf-8'))
    jobs = document['protocol']['jobs']
    outcomes = {}
    for path in (ROOT / 'outcomes').glob('*.json') if (ROOT / 'outcomes').is_dir() else ():
        try:
            outcomes[path.stem] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            outcomes[path.stem] = {'status': 'artifact_error'}
    claims = list((ROOT / 'claims').iterdir()) if (ROOT / 'claims').is_dir() else []
    states = []
    for worker_id in (0, 1):
        path = ROOT / f'worker-{worker_id}.health.json'
        state = json.loads(path.read_text()) if path.is_file() else {'status': 'not_started'}
        state['heartbeat_age_seconds'] = round(time.time() - state.get('heartbeat_unix', time.time()), 1)
        state['tmux_session_alive'] = subprocess.run([TMUX, '-L', SOCKET, 'has-session',
            '-t', f'worker-{worker_id}'], capture_output=True, timeout=10).returncode == 0
        states.append(state)
    task_states = Counter()
    metrics = {'tool_calls': 0, 'rounds': 0, 'redundant': 0, 'unknown': 0,
               'complete_metric_tasks': 0}
    for job in jobs:
        task_state = read_task_state(job)
        task_states[task_state.get('status', 'not_started')] += 1
        attempt = Path(task_state.get('attempt', ''))
        trace = attempt / 'snapshots' / 'cli-metrics.jsonl'
        if trace.is_file():
            try:
                from bestfgs.experiment_metrics import summarize_trace
                value = summarize_trace(trace)
                metrics['tool_calls'] += value['tool_calls']
                metrics['rounds'] += value['interaction_rounds']
                metrics['redundant'] += value['redundant_tool_calls']
                metrics['unknown'] += value['redundancy_unknown_calls']
                metrics['complete_metric_tasks'] += int(value['trace_complete'])
            except (OSError, ValueError, KeyError):
                pass
    print(json.dumps({'protocol_sha256': document['protocol_sha256'], 'N': COUNT,
        'outcomes': len(outcomes), 'claims': len(claims), 'task_states': dict(task_states),
        'workers': states, 'metrics_observed': metrics, 'official_evaluation': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'preflight', 'launch', 'worker', 'status'))
    parser.add_argument('--index', type=int, choices=(0, 1), default=0)
    parser.add_argument('--credential-stdin', action='store_true')
    arguments = parser.parse_args()
    try:
        key = None
        if arguments.credential_stdin:
            if arguments.action != 'launch':
                raise ValueError('Credentials are accepted only for explicit launch')
            payload = json.load(sys.stdin)
            key = payload.get('key', '').strip()
            if not key or any(character.isspace() for character in key):
                raise ValueError('Invalid credential format')
        if arguments.action == 'prepare':
            prepare()
        elif arguments.action == 'preflight':
            preflight(arguments.index)
        elif arguments.action == 'launch':
            launch(arguments.index, key)
        elif arguments.action == 'worker':
            worker(arguments.index)
        else:
            status(arguments.index)
    except Exception as error:
        # Never print request payloads, response bodies, environments or keys.
        print(json.dumps({'stage': arguments.action, 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, ValueError) else
                                     'Operation failed; no credentials logged'}))
        raise SystemExit(2)
