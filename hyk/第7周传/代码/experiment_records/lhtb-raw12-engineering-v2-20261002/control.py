"""Original twelve-task set, one pure RAW arm, no automatic replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from prepare import write, reserve
from resources import fits
from audit import verify

HERE = Path(__file__).resolve().parent
PYTHON = '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
MODEL = 'deepseek-flash'
METHODS = ['raw1']
PARALLEL_SLOTS = 4
sys.path[:0] = [str(HERE/'arms/common'), str(HERE/'arms/common/bestfgs-project/src'),
               str(HERE/'arms/common/hai-project/src'), str(HERE/'upstream/harbor/src')]


def group_options(method):
    if method not in METHODS:
        raise ValueError('Unknown exploration arm')
    return dict(memory_enabled=False, auto_memory=False, memory_decision=False,
        semantic_monitor=False, memory_reliability=False, monitor_reliability=False,
        outcome_reliability=True,
        stagnation_control=False, route_search=False,
        contrastive_mode='off',
        contrastive_threshold=.8)


def environment(method='raw1'):
    group_options(method)
    env = dict(os.environ)
    arm = HERE/'arms/common'
    env.update(PYTHONPATH=os.pathsep.join(map(str, [arm, arm/'bestfgs-project/src',
        arm/'hai-project/src', HERE, HERE/'upstream/harbor/src'])),
        HARBOR_TELEMETRY='0', HB_CONTINUE_MODE='same_conversation',
        HB_VERIFIER_FEEDBACK_MODE='binary', PYTHONUNBUFFERED='1',
        PYTHONDONTWRITEBYTECODE='1', LHTB_DISABLE_DISK_GUARD='1')
    env.pop('HB_PROCESS_REWARD', None)
    return env


def config(row, method, fixture=False):
    kwargs = dict(method='raw', task_id='fixture' if fixture else row['task'],
        wall_seconds=240 if fixture else row['agent']['timeout_sec'],
        cpu=row['environment']['cpus'], memory_mb=row['environment']['memory_mb'],
        fixture='budget' if fixture else False, **group_options(method))
    return dict(job_name=('fixture-' if fixture else '')+method+'-'+kwargs['task_id'],
        jobs_dir=str(HERE/('fixtures' if fixture else 'runs')), n_attempts=1,
        n_concurrent_trials=1, retry={'max_retries':0}, environment={'type':'docker','delete':True},
        agents=[dict(import_path='transport:TripleAgent', model_name=MODEL,
            override_setup_timeout_sec=600, kwargs=kwargs)],
        tasks=[dict(path=str(HERE/'fixture' if fixture else HERE/'upstream/tasks'/row['task']))])


def plan():
    from harbor.models.job.config import JobConfig
    manifest = json.loads((HERE/'manifest.json').read_text())
    reference = json.loads((HERE/'raw-reference-manifest.json').read_text())
    if manifest['tasks'] != reference['tasks'] or manifest['total_trials'] != 12 or manifest['methods'] != METHODS:
        raise RuntimeError('Must retain exactly the original twelve tasks and one pure RAW arm')
    (HERE/'jobs').mkdir(exist_ok=True)
    for row in manifest['tasks']:
        if not fits([row]*PARALLEL_SLOTS, cpu_cap=32, memory_cap_mb=64*1024, max_slots=8):
            raise RuntimeError('Parallel reservation does not fit')
        for method in METHODS:
            job = config(row, method)
            JobConfig.model_validate(job)
            write(HERE/'jobs'/(job['job_name']+'.json'), job)
    for method in METHODS:
        job = config(manifest['tasks'][0], method, True)
        JobConfig.model_validate(job)
        write(HERE/'jobs'/(job['job_name']+'.json'), job)
    print(json.dumps(dict(planned=12, tasks_per_arm=12, parallel_slots=PARALLEL_SLOTS, model_calls=0)))


def verify_image(task):
    row = next(r for r in json.loads((HERE/'images.json').read_text()) if r['task'] == task)
    info = json.loads(subprocess.check_output(['docker','image','inspect',row['image']]))[0]
    if info['Id'] != row['id'] or not any(x.endswith('@'+row['digest']) for x in info.get('RepoDigests',[])):
        raise RuntimeError('Original official image identity changed: '+task)


def cleanup_owned(root):
    from docker_state import LABEL
    for path in root.glob('*/agent/host-state/owned.json'):
        record = json.loads(path.read_text())
        for ident in record['containers']:
            result = subprocess.run(['docker','inspect',ident], capture_output=True, text=True)
            if result.returncode:
                continue
            if (json.loads(result.stdout)[0]['Config'].get('Labels') or {}).get(LABEL) != record['owner']:
                raise RuntimeError('Refuse cleanup of unowned container')
            subprocess.run(['docker','rm','-f',ident], capture_output=True, check=True)


def execute(row, method, fixture=False):
    if not fixture:
        validate()
        verify_image(row['task'])
    job = config(row, method, fixture)
    directory = Path(job['jobs_dir'])/job['job_name']
    if directory.exists():
        raise RuntimeError('Refuse replay of '+job['job_name'])
    timeout = 240 if fixture else row['agent']['timeout_sec']
    timeout += 600+(60 if fixture else row['verifier']['timeout_sec'])+300
    try:
        with (HERE/(job['job_name']+'.console.log')).open('x') as log:
            process = subprocess.Popen([PYTHON,str(HERE/'harbor_entry.py'),'run','--config',
                str(HERE/'jobs'/(job['job_name']+'.json'))], cwd=HERE, env=environment(method),
                stdout=log, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                raise RuntimeError('Host trial deadline exceeded')
        reports, logs = list(directory.glob('*/result.json')), list(directory.glob('*/agent/audit.jsonl'))
        if len(reports) != 1 or len(logs) != 1:
            raise RuntimeError('Missing/nonunique official report or audit')
        report = json.loads(reports[0].read_text())
        events = [json.loads(s) for s in logs[0].read_text().splitlines()]
        result = dict(task=row['task'], method=method, algorithm='raw', release='raw-cli-engineering-v2',
            report=str(reports[0]), verifier_result=report.get('verifier_result'),
            exception_info=report.get('exception_info'), process_exit_code=code, audit_chain=verify(logs[0]))
        if fixture:
            reward = (report.get('verifier_result') or {}).get('rewards') or {}
            metadata = (report.get('agent_result') or {}).get('metadata') or {}
            if code or report.get('exception_info') or not reward or min(reward.values()) < 1 or metadata.get('continue_until_timeout_phases',0) < 1:
                raise RuntimeError('Official continuation/isolation fixture failed')
        else:
            utilization = [e['utilization'] for e in events if e.get('event') == 'mechanism_utilization']
            if len(utilization) > 1:
                raise RuntimeError('Nonunique utilization summary')
            endings = [e.get('result',{}) for e in events if e.get('event') == 'method_end']
            # An accepted submit can end Harbor while the actor waits on binary
            # feedback. Preserve audited counts; never mislabel acceptance as
            # a missing instrumentation failure or invent a completed solver loop.
            observed_counts=dict(model_requests=sum(e.get('event')=='model_request' for e in events),
                tool_calls=sum(e.get('event')=='tool_call' for e in events),
                advisor_calls=0,monitor_calls=0,memories_admitted=0,memory_exposures=0,
                contrastive_rejections=0,source='outer_audit_not_solver_final')
            result.update(mechanism_utilization=utilization[0] if utilization else observed_counts,
                group='raw', repetition=1,
                model_usage=endings[-1].get('model_usage',{}) if endings else {},
                wall_seconds=endings[-1].get('wall_seconds') if endings else None)
            if not endings and not report.get('exception_info') and min(
                    ((report.get('verifier_result') or {}).get('rewards') or {'unknown':0}).values()) >= 1:
                result['stop_reason']='official_acceptance'
            inner_path = reports[0].parent/'agent/method/events.jsonl'
            if inner_path.exists():
                from bestfgs.lean_audit import read_trace
                inner = read_trace(inner_path)
                errors = [e for e in inner if e['event'] == 'protocol_error']
                result['contrastive_gate_limit'] = bool(endings and endings[-1].get('stop_reason') ==
                    'model_or_protocol_error_limit' and len(errors) >= 3 and all(
                        e.get('protocol_error','').startswith('contrastive rejection:') for e in errors[-3:]))
                result['contrastive_gate_reasons'] = [e['reason'] for e in inner
                    if e['event'] == 'contrastive_validation' and not e['accepted']]
                result['exploration_episode_count'] = sum(e['event'] == 'contrastive_episode_start' for e in inner)
        return result
    finally:
        cleanup_owned(directory)


def source_hashes():
    paths = [p for p in HERE.iterdir() if p.is_file() and (p.suffix in ('.py','.ps1','.txt') or
        p.name in ('manifest.json','raw-reference-manifest.json','candidate-source-manifest.json',
            'prior-results.json','images.json','verified-digests.json','run-scope.json'))]
    for name in ('arms','upstream/harbor/src','jobs','fixture','tests'):
        paths.extend(p for p in (HERE/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts)
    for row in json.loads((HERE/'manifest.json').read_text())['tasks']:
        paths.extend(p for p in (HERE/'upstream/tasks'/row['task']).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return {str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def validate():
    ready = json.loads((HERE/'ready.json').read_text())
    if ready.get('ready') is not True or ready['source_hashes'] != source_hashes():
        raise RuntimeError('Readiness gate incomplete or sealed inputs changed')
    return ready


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['plan','fixture','validate'])
    parser.add_argument('--method', choices=METHODS, default=METHODS[0])
    args = parser.parse_args()
    if args.mode == 'plan': plan()
    elif args.mode == 'validate': print(json.dumps(dict(ready=bool(validate()))))
    else: print(json.dumps(execute(json.loads((HERE/'manifest.json').read_text())['tasks'][0], args.method, True)))
