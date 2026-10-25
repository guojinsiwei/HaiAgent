"""Frozen six-task pilot, one task container at a time, no automatic whole-task retries."""
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
SHARED = Path('/mnt/sdb/home/lizh639/terminalbench-v14-setup')
PYTHON = str(SHARED / 'runtime/bin/python')
HARBOR = str(SHARED / 'runtime/bin/harbor')
sys.path.insert(0, str(HERE / 'project/src'))
from haiagent.metrics import load_run, prepare_audit, summarize_run, summarize_manifest
from haiagent.storage import atomic_json, digest


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def files(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


def environment():
    # The shared module contains only the existing offline verifier dependency adapter.
    return dict(os.environ, PYTHONPATH=os.pathsep.join([str(HERE), str(SHARED), str(HERE / 'project/src')]),
                HARBOR_TELEMETRY='0', PYTHONUNBUFFERED='1')


def freeze():
    from harbor.models.job.config import JobConfig
    if (HERE / 'protocol.json').exists():
        raise RuntimeError('Already frozen; refusing to rewrite')
    original = json.loads((SHARED / 'task-selection.json').read_text())
    selected = sorted(original['tasks'], key=lambda t: t['id'])
    random.Random(20260926).shuffle(selected)
    selected = selected[:6]
    old_protocol = json.loads((SHARED / 'experiment/control/protocol.json').read_text())['protocol']
    old_tasks = {t['id']: t for t in old_protocol['tasks']}
    preflight = json.loads((SHARED / 'offline-preflight-summary.json').read_text())
    if not preflight.get('complete'):
        raise RuntimeError('Shared offline verifier dependency preflight incomplete')
    tasks, jobs = [], []
    (HERE / 'jobs').mkdir()
    for index, item in enumerate(selected):
        task = old_tasks[item['id']]
        if files(Path(task['path'])) != task['pinned_files']:
            raise RuntimeError('Existing pinned task changed')
        inspect = subprocess.run(['docker', 'image', 'inspect', task['pinned_image']], check=True,
                                 capture_output=True, text=True)
        image = json.loads(inspect.stdout)[0]
        tasks.append({'id': item['id'], 'path': task['path'], 'image': task['pinned_image'],
                      'image_id': image['Id'], 'files': task['pinned_files'],
                      'agent_seconds': item['agent_timeout'], 'verifier_seconds': item['verifier_timeout']})
        for method in (['hai', 'raw'] if index % 2 == 0 else ['raw', 'hai']):
            name = f"{index:02d}-{item['id'].split('/')[-1]}-{method}"
            config = job_config(name, tasks[-1], method)
            JobConfig.model_validate(config)
            path = HERE / 'jobs' / (name + '.json')
            atomic_json(path, config)
            jobs.append({'name': name, 'task_id': item['id'], 'method': method,
                         'config': str(path), 'config_sha256': sha(path),
                         'watchdog_seconds': item['agent_timeout'] + 2 * item['verifier_timeout'] + 1800})
    protocol = {'version': 'hai-terminal6-pilot-v3', 'purpose': 'development/integration pilot, not held-out scientific evidence',
                'agent_version': '0.4.0', 'response_protocol': 'tool_call', 'thinking': 'disabled',
                'hai_memory_policy': 'three identical complete outputs -> evidenced observation and decision advice; same-action retry requires reason; no extra model calls or budgets',
                'max_consecutive_format_errors': 3, 'max_format_errors': 8,
                'restart_policy': 'fresh 12 runs; prior 0.2.0/0.3.0 data excluded; no task replay',
                'selection_seed': 20260926, 'selection_rule': 'sort prior non-frozen 36-task development selection then seeded shuffle, first 6; no outcome filtering',
                'selection_source_sha256': sha(SHARED / 'task-selection.json'), 'tasks': tasks, 'jobs': jobs,
                'model': 'deepseek-flash', 'endpoint': 'https://api.deepseek.com', 'task_count': 6, 'run_count': 12,
                'max_concurrency': 1, 'task_retries': 0, 'minimum_free_disk_gib': 40,
                'budgets': {'turns': 80, 'tools': 70, 'output_bytes': 16000, 'prompt_bytes': 48000,
                            'max_tokens_per_response': 4096, 'temperature': 0, 'api_attempts': 2,
                            'wall_seconds': 'each original public task agent limit', 'command_seconds': 120,
                            'request_seconds': 180, 'equal_total_token_budget': False},
                'success': 'official Harbor verifier binary reward, without harness exception; submission alone is not success',
                'rounds': 'all strategy responses including submit/format errors; transport retries separate',
                'redundancy': 'offline contextual avoidability audit; unreviewed=null, never mechanical repetition rate',
                'source_files': files(HERE / 'project/src'),
                'transport_files': {n: sha(HERE / n) for n in ('transport.py', 'runner.py', 'control.py', 'launch.py')},
                'shared_verifier_files': {n: sha(SHARED / n) for n in ('offline_verifier.py', 'offline-cache-manifest.json', 'offline-preflight-summary.json')},
                'harbor_version': importlib.metadata.version('harbor')}
    atomic_json(HERE / 'protocol.json', {'protocol': protocol, 'sha256': digest(protocol)})
    print(json.dumps({'frozen': True, 'tasks': [t['id'] for t in tasks], 'runs': 12, 'sha256': digest(protocol)}))


def job_config(name, task, method, fixture=False):
    wall = 60 if fixture else task['agent_seconds']
    return {'job_name': name, 'jobs_dir': str(HERE / ('preflight-runs' if fixture else 'runs')),
            'n_attempts': 1, 'n_concurrent_trials': 1, 'retry': {'max_retries': 0},
            'timeout_multiplier': 1, 'verifier_timeout_multiplier': 2,
            'environment': {'type': 'docker', 'delete': True},
            'verifier': {'import_path': 'offline_verifier:OfflineVerifier'},
            'agents': [{'import_path': 'transport:HAIAgent', 'model_name': 'deepseek-flash',
                        'override_timeout_sec': wall + 120, 'override_setup_timeout_sec': 600,
                        'extra_allowed_hosts': ['api.deepseek.com'],
                        'kwargs': {'method': method, 'task_id': task['id'], 'wall_seconds': wall, 'fixture': fixture}}],
            'tasks': [{'path': task['path']}]}


def validate():
    wrapped = json.loads((HERE / 'protocol.json').read_text())
    p = wrapped['protocol']
    if digest(p) != wrapped['sha256'] or files(HERE / 'project/src') != p['source_files']:
        raise RuntimeError('Frozen source/protocol mismatch')
    for name, expected in p['transport_files'].items():
        if sha(HERE / name) != expected:
            raise RuntimeError('Frozen transport mismatch')
    for name, expected in p['shared_verifier_files'].items():
        if sha(SHARED / name) != expected:
            raise RuntimeError('Shared verifier changed')
    if importlib.metadata.version('harbor') != p['harbor_version']:
        raise RuntimeError('Harbor version changed')
    for task in p['tasks']:
        if files(Path(task['path'])) != task['files']:
            raise RuntimeError('Pinned task/verifier changed')
    for job in p['jobs']:
        if sha(job['config']) != job['config_sha256']:
            raise RuntimeError('Job config changed')
    return wrapped


def unique_trial(directory):
    paths = []
    for path in directory.glob('*/result.json'):
        data = json.loads(path.read_text())
        if data.get('task_name') and data.get('finished_at'):
            paths.append(path)
    if len(paths) != 1:
        raise RuntimeError('Missing or non-unique final Harbor trial; no automatic replay')
    return paths[0]


def official_outcome(source, task_id):
    if source.get('task_name') != task_id or not source.get('finished_at'):
        raise ValueError('Harbor report identity/completion mismatch')
    if source.get('exception_info'):
        raise ValueError('Harbor infrastructure/timeout exception; outcome requires review')
    reward = (source.get('verifier_result') or {}).get('rewards', {}).get('reward')
    if type(reward) not in (int, float) or reward not in (0, 1):
        raise ValueError('Missing/non-binary official reward')
    return reward == 1


def collect(job, trial_path):
    source = json.loads(trial_path.read_text())
    success = official_outcome(source, job['task_id'])
    runtime = trial_path.parent / 'agent/haia-run'
    result, _ = load_run(runtime)
    if result['task_id'] != job['task_id'] or result['method'] != job['method']:
        raise ValueError('Runtime/job mismatch')
    evaluation = {'schema': 'hai-harbor-binding-v1', 'run_id': result['run_id'], 'task_id': result['task_id'],
                  'artifact_sha256': (result.get('artifact') or {}).get('sha256'), 'success': success,
                  'source_report': str(trial_path.relative_to(HERE)), 'source_sha256': sha(trial_path),
                  'runtime_trace_sha256': result['trace_sha256'], 'official_reward': int(success)}
    destination = runtime / 'harbor-evaluation.json'
    if destination.exists() and json.loads(destination.read_text()) != evaluation:
        raise ValueError('Existing official binding changed')
    atomic_json(destination, evaluation)
    if not (runtime / 'contextual-audit.json').exists():
        prepare_audit(runtime, runtime / 'contextual-audit.json')
    summary = summarize_run(runtime)
    return summary | {'success': success, 'official_reward': int(success), 'run_dir': str(runtime),
                      'harbor_report_sha256': evaluation['source_sha256']}


def report():
    p = validate()['protocol']
    rows = []
    for job in p['jobs']:
        directory = HERE / 'runs' / job['name']
        row = {'task_id': job['task_id'], 'method': job['method'], 'success': None, 'state': 'not_started'}
        if directory.exists():
            try:
                row.update(collect(job, unique_trial(directory)), state='completed')
            except (ValueError, RuntimeError, OSError, KeyError) as exc:
                row.update(state='needs_review', error=str(exc))
        rows.append(row)
    groups = {}
    for method in ('hai', 'raw'):
        selected = [r for r in rows if r['method'] == method]
        scored = [r for r in selected if r['success'] is not None]
        groups[method] = {'planned': 6, 'scored': len(scored), 'successes': sum(r['success'] for r in scored),
                          'success_rate': sum(r['success'] for r in scored) / 6 if len(scored) == 6 else None,
                          'average_interaction_rounds': sum(r['interaction_rounds'] for r in scored) / 6 if len(scored) == 6 else None,
                          'tool_redundancy_rate': None, 'redundancy_status': 'requires_contextual_audit'}
    atomic_json(HERE / 'summary.json', {'groups': groups, 'rows': rows})
    return groups


def preflight():
    p = validate()['protocol']
    env = environment()
    test = subprocess.run([PYTHON, '-B', '-m', 'unittest', 'discover', '-s', str(HERE / 'project/tests'), '-v'],
                          env=env, capture_output=True, text=True, timeout=180)
    (HERE / 'linux-tests.log').write_text(test.stdout + test.stderr)
    if test.returncode:
        raise RuntimeError('Linux regression suite failed; see linux-tests.log')
    task = next(t for t in p['tasks'] if t['id'] == 'terminal-bench/log-summary-date-ranges')
    checks = []
    for method in ('hai', 'raw'):
        name = 'offline-fixture-' + method
        config = job_config(name, task, method, fixture=True)
        config_path = HERE / (name + '.json')
        atomic_json(config_path, config)
        directory = HERE / 'preflight-runs' / name
        if directory.exists():
            raise RuntimeError('Preflight output already exists; inspect rather than overwrite')
        with (HERE / (name + '.log')).open('x') as log:
            completed = subprocess.run([HARBOR, 'run', '--config', str(config_path)], env=env,
                                       cwd=HERE, stdout=log, stderr=subprocess.STDOUT, timeout=2400)
        path = unique_trial(directory)
        source = json.loads(path.read_text())
        official_outcome(source, task['id'])
        result, trace = load_run(path.parent / 'agent/haia-run')
        if completed.returncode or not result['submitted'] or result['tool_calls'] != 1 or any(r['event'] == 'api_start' for r in trace):
            raise RuntimeError('Offline adapter fixture failed')
        checks.append({'method': method, 'official_verifier_executed': True, 'model_calls': 0,
                       'report': str(path), 'report_sha256': sha(path)})
    atomic_json(HERE / 'ready.json', {'ready': True, 'protocol_sha256': validate()['sha256'],
                                     'linux_tests_sha256': sha(HERE / 'linux-tests.log'), 'fixtures': checks})
    print(json.dumps({'ready_for_key': True, 'model_calls': 0}))


def run(credential):
    with (HERE / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        wrapped = validate()
        ready = json.loads((HERE / 'ready.json').read_text())
        if not ready['ready'] or ready['protocol_sha256'] != wrapped['sha256']:
            raise RuntimeError('Current protocol did not pass preflight')
        path = Path(credential)
        key = path.read_text().strip()
        path.unlink()
        path.parent.rmdir()
        env = environment() | {'DEEPSEEK_API_KEY': key}
        state = {'state': 'running', 'pid': os.getpid(), 'completed': 0, 'total': 12,
                 'protocol_sha256': wrapped['sha256']}
        stop = threading.Event()
        def heartbeat():
            while not stop.is_set():
                atomic_json(HERE / 'health.json', state | {'heartbeat': time.time()})
                stop.wait(20)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        process = None
        try:
            for job in wrapped['protocol']['jobs']:
                directory = HERE / 'runs' / job['name']
                if directory.exists():
                    collect(job, unique_trial(directory))  # validated complete only; never replay
                    state['completed'] += 1
                    continue
                validate()
                if shutil.disk_usage(HERE).free < 40 * 1024**3:
                    raise RuntimeError('Disk guard: less than 40 GiB available')
                state.update(current=job['name'], started_at=time.time())
                with (HERE / (job['name'] + '.log')).open('x') as log:
                    process = subprocess.Popen([HARBOR, 'run', '--config', job['config']], cwd=HERE, env=env,
                                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    state['child_pid'] = process.pid
                    deadline = time.monotonic() + job['watchdog_seconds']
                    while process.poll() is None:
                        if time.monotonic() > deadline or shutil.disk_usage(HERE).free < 40 * 1024**3:
                            raise RuntimeError('Watchdog/disk guard interrupted current trial; no replay')
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            pass
                collect(job, unique_trial(directory))
                if process.returncode:
                    raise RuntimeError('Harbor job returned nonzero')
                state['completed'] += 1
                report()
            state.update(state='completed', current=None, child_pid=None)
        except Exception as exc:
            state.update(state='needs_attention', error=str(exc))
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            raise
        finally:
            stop.set()
            thread.join()
            atomic_json(HERE / 'health.json', state | {'heartbeat': time.time()})
            report()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['freeze', 'validate', 'preflight', 'run', 'report'])
    parser.add_argument('--credential')
    args = parser.parse_args()
    if args.action == 'run':
        run(args.credential)
    else:
        value = globals()[args.action]()
        if args.action in ('validate', 'report'):
            print(json.dumps({'valid': True, 'sha256': value['sha256']} if args.action == 'validate' else value))
