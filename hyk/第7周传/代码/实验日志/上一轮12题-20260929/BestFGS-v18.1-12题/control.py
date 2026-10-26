"""BestFGS v18.1 only: one bounded worker, no trial replay."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from prepare import write, reserve
from resources import fits
from audit import verify

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / 'bestfgs-project/src'), str(HERE / 'hai-project/src')]
PYTHON = '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
MODEL = 'deepseek-flash'
METHODS = ['bestfgs']
PARALLEL_SLOTS = 1

def environment():
    env = dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join(map(str, [HERE, HERE / 'upstream/harbor/src',
        HERE / 'bestfgs-project/src', HERE / 'hai-project/src'])), HARBOR_TELEMETRY='0',
        HB_CONTINUE_MODE='same_conversation', HB_VERIFIER_FEEDBACK_MODE='binary', PYTHONUNBUFFERED='1')
    env.pop('HB_PROCESS_REWARD', None)
    return env

def config(row, method, fixture=False):
    task = 'fixture' if fixture else row['task']
    wall = 240 if fixture else row['agent']['timeout_sec']
    name = ('fixture5-' if fixture else '') + method + '-' + task
    return {'job_name': name, 'jobs_dir': str(HERE / ('fixtures' if fixture else 'runs')),
        'n_attempts': 1, 'n_concurrent_trials': 1, 'retry': {'max_retries': 0},
        'environment': {'type': 'docker', 'delete': True},
        'agents': [{'import_path': 'transport:TripleAgent', 'model_name': MODEL,
                    'override_setup_timeout_sec': 600,
                    'kwargs': {'method': method, 'task_id': task, 'wall_seconds': wall,
                               'cpu': row['environment']['cpus'], 'memory_mb': row['environment']['memory_mb'],
                               'fixture': 'budget' if fixture else False}}],
        'tasks': [{'path': str(HERE / 'fixture' if fixture else HERE / 'upstream/tasks' / task)}]}

def plan():
    from harbor.models.job.config import JobConfig
    manifest = json.loads((HERE / 'manifest.json').read_text())
    if len(manifest['tasks']) != 12 or manifest['total_trials'] != 12:
        raise RuntimeError('Expected fixed 12-task BestFGS-v18.1-only protocol')
    (HERE / 'jobs').mkdir(exist_ok=True)
    for row in manifest['tasks']:
        if not fits([row] * PARALLEL_SLOTS):
            raise RuntimeError('Parallel resource reservation exceeds limits')
        for method in METHODS:
            job = config(row, method)
            JobConfig.model_validate(job)
            write(HERE / 'jobs' / (job['job_name'] + '.json'), job)
    for method in METHODS:
        job = config(manifest['tasks'][0], method, True)
        JobConfig.model_validate(job)
        write(HERE / 'jobs' / (job['job_name'] + '.json'), job)
    print(json.dumps({'planned': 12, 'parallel_slots': PARALLEL_SLOTS, 'model_calls': 0}))

def cleanup_owned(root):
    # No prune, no name glob deletion. Verify every ID against its ownership label.
    from docker_state import LABEL
    for journal in root.glob('*/agent/host-state/owned.json'):
        data = json.loads(journal.read_text())
        for container in data['containers']:
            p = subprocess.run(['docker', 'inspect', container], capture_output=True, text=True)
            if p.returncode:
                continue
            info = json.loads(p.stdout)[0]
            if (info['Config'].get('Labels') or {}).get(LABEL) != data['owner']:
                raise RuntimeError('Refusing container cleanup: owner mismatch')
            subprocess.run(['docker', 'rm', '-f', container], check=True, capture_output=True)
        # Keep filesystem images/mirrors until auditing/retention policy is finalized.

def execute(row, method, fixture=False):
    reserve()
    job = config(row, method, fixture)
    directory = Path(job['jobs_dir']) / job['job_name']
    if directory.exists():
        raise RuntimeError('Refusing replay of existing job ' + job['job_name'])
    command = [PYTHON, str(HERE / 'harbor_entry.py'), 'run',
               '--config', str(HERE / 'jobs' / (job['job_name'] + '.json'))]
    wall = 240 if fixture else row['agent']['timeout_sec']
    timeout = wall + 600 + (60 if fixture else row['verifier']['timeout_sec']) + 300
    try:
        with (HERE / (job['job_name'] + '.console.log')).open('x') as log:
            process = subprocess.Popen(command, cwd=HERE, env=environment(), stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise RuntimeError('Host trial deadline exceeded')
        reports = list(directory.glob('*/result.json'))
        if len(reports) != 1:
            raise RuntimeError('Missing or nonunique official trial report')
        report = json.loads(reports[0].read_text())
        logs = list(directory.glob('*/agent/audit.jsonl'))
        if len(logs) != 1:
            raise RuntimeError('Missing method audit log')
        chain = verify(logs[0])
        value = {'task': row['task'], 'method': method, 'report': str(reports[0]),
                 'verifier_result': report.get('verifier_result'), 'exception_info': report.get('exception_info'),
                 'process_exit_code': code, 'audit_chain': chain}
        events = [json.loads(line) for line in logs[0].read_text().splitlines()]
        utilization = [e.get('utilization') for e in events
                       if e.get('event') == 'mechanism_utilization']
        if not fixture and method in {'bestfgs', 'hai', 'raw'}:
            if len(utilization) != 1 or not isinstance(utilization[0], dict):
                raise RuntimeError('Missing or nonunique mechanism utilization summary')
            value['mechanism_utilization'] = utilization[0]
        if fixture:
            reward = (report.get('verifier_result') or {}).get('rewards') or {}
            metadata = (report.get('agent_result') or {}).get('metadata') or {}
            if not reward or min(reward.values()) < 1 or metadata.get('continue_until_timeout_phases', 0) < 1:
                raise RuntimeError('Official continuation/isolation fixture failed')
        return value
    finally:
        cleanup_owned(directory)

def source_hashes():
    paths = [HERE / name for name in ('manifest.json', 'transport.py', 'docker_state.py',
             'container_command.py', 'candidate.py', 'audit.py', 'resources.py', 'control.py', 'prepare.py', 'harbor_entry.py',
             'launch_supervised.py', 'supervisor.py', 'preflight.py', 'images.json',
             'verified-digests.json', 'PROTOCOL.md', 'prior-results.json', 'durable.py',
             'outcomes.py', 'test_outcomes.py', 'test_durable.py', 'test_supervisor.py',
             'test_adaptation.py', 'test_control.py', 'test_audit.py',
             'test_harness_patch.py')]
    for name in ('bestfgs-project/src', 'hai-project/src', 'upstream/harbor/src', 'jobs'):
        paths += [p for p in (HERE / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for row in json.loads((HERE / 'manifest.json').read_text())['tasks']:
        paths += [p for p in (HERE / 'upstream/tasks' / row['task']).rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts]
    return {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

def validate():
    ready = json.loads((HERE / 'ready.json').read_text())
    if ready.get('ready') is not True or ready.get('source_hashes') != source_hashes():
        raise RuntimeError('Readiness gate incomplete or frozen source changed')
    return ready

def run_all(credential):
    with (HERE / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        validate()
        if (HERE / 'health.json').exists():
            raise RuntimeError('Already started; explicit inspected resume required')
        path = Path(credential)
        try:
            os.environ['DEEPSEEK_API_KEY'] = path.read_text().strip()
        finally:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        manifest = json.loads((HERE / 'manifest.json').read_text())
        prior = HERE / 'prior-results.json'
        rows = json.loads(prior.read_text()) if prior.exists() else []
        completed = {(r['task'], r['method']) for r in rows}
        allowed = {(t['task'], m) for t in manifest['tasks'] for m in METHODS}
        if len(completed) != len(rows) or not completed.issubset(allowed) or any(r.get('exception_info') or r.get('verifier_result') is None for r in rows):
            raise RuntimeError('Invalid carried-forward results')
        pending, active = [], {}
        stopped = False
        protocol_hash = validate()['protocol_sha256']
        for i, task in enumerate(manifest['tasks']):
            offset = i % len(METHODS)
            order = METHODS[offset:] + METHODS[:offset]
            pending.extend((task, method) for method in order if (task['task'], method) not in completed)
        def health(state):
            write(HERE / 'health.json', {'state': state, 'updated': time.time(),
                'completed': len(rows), 'total': 12, 'pending': len(pending),
                'active': [{'task': t['task'], 'method': m} for t, m in active.values()],
                'protocol_sha256': protocol_hash})
        try:
            health('running')
            with ThreadPoolExecutor(max_workers=PARALLEL_SLOTS) as pool:
                while active or (pending and not stopped):
                    while pending and len(active) < PARALLEL_SLOTS and not stopped:
                        try:
                            reserve()
                            validate()
                        except Exception:
                            stopped = True
                            break
                        task, method = pending.pop(0)
                        active[pool.submit(execute, task, method)] = (task, method)
                    if not active:
                        break
                    done, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
                    for future in done:
                        task, method = active.pop(future)
                        try:
                            result = future.result()
                            exception = result.get('exception_info') or {}
                            if exception and exception.get('exception_type') not in ('AgentTimeoutError',):
                                stopped = True
                            if result['process_exit_code'] != 0:
                                stopped = True
                            audit_path = Path(result['report']).parent / 'agent/audit.jsonl'
                            events = [json.loads(line) for line in audit_path.read_text().splitlines()]
                            normal_wall_stop = any(e.get('event') == 'method_end' and
                                e.get('stop_reason') == 'wall_budget_exhausted' for e in events)
                            if any(e.get('event') == 'adapter_error' for e in events):
                                stopped = True
                            rows.append(result)
                        except Exception as error:
                            stopped = True
                            rows.append({'task': task['task'], 'method': method,
                                         'infrastructure_error': type(error).__name__})
                        write(HERE / 'summary.json', rows)
                    health('draining_after_error' if stopped else 'running')
            health('needs_attention' if stopped else 'completed')
        finally:
            os.environ.pop('DEEPSEEK_API_KEY', None)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['plan', 'fixture', 'validate', 'run'])
    parser.add_argument('--method', default='bestfgs', choices=METHODS)
    parser.add_argument('--credential')
    args = parser.parse_args()
    if args.mode == 'plan':
        plan()
    elif args.mode == 'fixture':
        row = json.loads((HERE / 'manifest.json').read_text())['tasks'][0]
        print(json.dumps(execute(row, args.method, True)))
    elif args.mode == 'validate':
        print(json.dumps({'ready': bool(validate())}))
    else:
        run_all(args.credential)
