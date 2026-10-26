"""Three independent single-shot Raw diagnostics; never auto-replay a trial."""
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SHARED = Path('/mnt/sdb/home/lizh639/terminalbench-v14-setup')
PYTHON = str(SHARED / 'runtime/bin/python')
HARBOR = str(SHARED / 'runtime/bin/harbor')
sys.path.insert(0, str(HERE / 'project/src'))
from haiagent.storage import atomic_json, digest
from prepare import TASKS

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def files(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}

def environment():
    return dict(os.environ, PYTHONPATH=str(HERE) + os.pathsep + str(HERE / 'project/src'),
                HARBOR_TELEMETRY='0', PYTHONUNBUFFERED='1')

def config(task, fixture=False):
    wall = 60 if fixture else 5400
    name = ('fixture-' if fixture else 'raw-') + task
    return {'job_name': name, 'jobs_dir': str(HERE / ('preflight-runs' if fixture else 'runs')),
            'n_attempts': 1, 'n_concurrent_trials': 1, 'retry': {'max_retries': 0},
            'environment': {'type': 'docker', 'delete': True}, 'verifier': {'disable': True},
            'agents': [{'import_path': 'transport:HAIAgent', 'model_name': 'deepseek-flash',
                        'override_timeout_sec': wall + 120, 'override_setup_timeout_sec': 600,
                        'extra_allowed_hosts': ['api.deepseek.com'],
                        'kwargs': {'method': 'raw', 'task_id': 'long-horizon-terminal-bench/' + task,
                                   'wall_seconds': wall, 'fixture': fixture}}],
            'tasks': [{'path': str(HERE / 'upstream/tasks' / task)}]}

def freeze():
    from harbor.models.job.config import JobConfig
    if (HERE / 'protocol.json').exists():
        raise RuntimeError('Already frozen')
    images = json.loads((HERE / 'images.json').read_text())
    if [i['task'] for i in images] != TASKS:
        raise RuntimeError('Images incomplete')
    (HERE / 'jobs').mkdir(exist_ok=True)
    for task in TASKS:
        for fixture in (True, False):
            job = config(task, fixture)
            JobConfig.model_validate(job)
            atomic_json(HERE / 'jobs' / (job['job_name'] + '.json'), job)
    protocol = {'version': 'lhtb-raw3-diagnostic-1', 'method': 'raw', 'model': 'deepseek-flash',
                'endpoint': 'https://api.deepseek.com', 'thinking': 'disabled',
                'purpose': 'loop observation, not official leaderboard evaluation or benchmark comparison',
                'selection': '3 public CPU-only tasks selected for migration, iterative numerical optimization, and repository optimization; no model-outcome filtering',
                'budgets': {'wall_seconds': 5400, 'max_tools': 300, 'max_turns': 320,
                            'command_seconds': 900, 'prompt_bytes': 48000, 'output_bytes': 16000,
                            'max_tokens': 4096, 'temperature': 0, 'api_attempts': 2},
                'policy': 'autonomous submit; no memory, loop intervention, verifier feedback or task retries; official continue-until-timeout explicitly overridden',
                'success': None, 'scoring': 'verifier disabled; submission is not official success',
                'task_commit': subprocess.check_output(['git', '-C', str(HERE / 'upstream'), 'rev-parse', 'HEAD'], text=True).strip(),
                'tasks': TASKS, 'images': images, 'source': files(HERE / 'project/src'),
                'task_files': {task: files(HERE / 'upstream/tasks' / task) for task in TASKS},
                'control_files': {n: sha(HERE / n) for n in ('control.py', 'transport.py', 'runner.py', 'launch.py', 'prepare.py')},
                'job_files': files(HERE / 'jobs'), 'harbor_version': importlib.metadata.version('harbor')}
    atomic_json(HERE / 'protocol.json', {'protocol': protocol, 'sha256': digest(protocol)})

def validate():
    wrapped = json.loads((HERE / 'protocol.json').read_text())
    p = wrapped['protocol']
    if digest(p) != wrapped['sha256'] or files(HERE / 'project/src') != p['source']:
        raise RuntimeError('Protocol/source changed')
    for name, expected in p['control_files'].items():
        if sha(HERE / name) != expected:
            raise RuntimeError('Control changed: ' + name)
    if files(HERE / 'jobs') != p['job_files']:
        raise RuntimeError('Job configuration changed')
    if importlib.metadata.version('harbor') != p['harbor_version']:
        raise RuntimeError('Harbor version changed')
    for task in p['tasks']:
        if files(HERE / 'upstream/tasks' / task) != p['task_files'][task]:
            raise RuntimeError('Task changed')
    for image in p['images']:
        actual = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image['image']]))[0]
        if actual['Id'] != image['id']:
            raise RuntimeError('Image changed')
    return wrapped

def result_for(task, fixture):
    job = config(task, fixture)
    root = Path(job['jobs_dir']) / job['job_name']
    results = list(root.glob('*/agent/haia-run/result.json'))
    reports = list(root.glob('*/result.json'))
    if len(results) != 1 or len(reports) != 1:
        raise RuntimeError('Missing/non-unique trial result: ' + task)
    report = json.loads(reports[0].read_text())
    if report.get('exception_info') or not report.get('finished_at'):
        raise RuntimeError('Harbor trial error: ' + task)
    value = json.loads(results[0].read_text())
    if value['method'] != 'raw' or value['task_id'] != 'long-horizon-terminal-bench/' + task:
        raise RuntimeError('Result identity mismatch')
    return {k: value.get(k) for k in ('task_id', 'submitted', 'stop_reason', 'interaction_rounds', 'tool_calls')} | {
        'official_success': None, 'run_dir': str(results[0].parent)}

def execute(task, fixture=False, completed=None):
    if min(shutil.disk_usage('/var/lib/docker').free, shutil.disk_usage(HERE).free) < 40 * 2**30:
        raise RuntimeError('Disk reserve below 40 GiB')
    job = config(task, fixture)
    root = Path(job['jobs_dir']) / job['job_name']
    if root.exists():
        raise RuntimeError('Job already exists; refusing automatic replay: ' + task)
    with (HERE / (job['job_name'] + '.log')).open('x') as log:
        process = subprocess.Popen([HARBOR, 'run', '--config', str(HERE / 'jobs' / (job['job_name'] + '.json'))],
                                   env=environment(), cwd=HERE, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic() - started > (1200 if fixture else 6600):
                    raise RuntimeError('Host watchdog expired')
                if not fixture:
                    atomic_json(HERE / 'health.json', {'state': 'running', 'updated': time.time(),
                        'pid': os.getpid(), 'child_pid': process.pid, 'task': task, 'completed': completed or []})
                time.sleep(10)
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            raise
        if process.returncode:
            raise RuntimeError(f'Harbor exited {process.returncode}: {task}')
    result = result_for(task, fixture)
    if fixture and (result['tool_calls'] != 1 or not result['submitted']):
        raise RuntimeError('Fixture feedback failed')
    return result

def preflight():
    wrapped = validate()
    rows = [execute(task, True) for task in TASKS]
    atomic_json(HERE / 'ready.json', {'ready': True, 'protocol_sha256': wrapped['sha256'], 'fixtures': rows,
                                     'model_calls': 0})

def run(credential):
    with (HERE / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = Path(credential)
        try:
            os.environ['DEEPSEEK_API_KEY'] = path.read_text().strip()
        finally:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        rows = []
        try:
            validate()
            for task in TASKS:
                rows.append(execute(task, completed=rows))
                atomic_json(HERE / 'summary.json', {'rows': rows, 'official_success': None})
            atomic_json(HERE / 'health.json', {'state': 'completed', 'updated': time.time(), 'completed': rows})
        except BaseException as error:
            atomic_json(HERE / 'health.json', {'state': 'needs_attention', 'updated': time.time(),
                        'error': type(error).__name__ + ': ' + str(error), 'completed': rows})
            raise
        finally:
            os.environ.pop('DEEPSEEK_API_KEY', None)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['freeze', 'preflight', 'validate', 'run'])
    parser.add_argument('--credential')
    args = parser.parse_args()
    if args.mode == 'run':
        run(args.credential)
    else:
        globals()[args.mode]()
