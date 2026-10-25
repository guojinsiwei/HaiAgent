"""One paired experiment: immutable v6/v7 sources, eight common tasks, no replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from prepare import write,reserve
from resources import fits
from audit import verify

HERE=Path(__file__).resolve().parent
PYTHON='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
MODEL='deepseek-flash'
METHODS=['A1']
PARALLEL_SLOTS=4
sys.path[:0]=[str(HERE/'arms/common'),str(HERE/'arms/common/bestfgs-project/src'),str(HERE/'arms/common/hai-project/src')]

def group_options(group):
    if group not in 'ABCDE' or len(group)!=1:raise ValueError('Invalid group')
    return dict(memory_enabled=group!='A',auto_memory=group!='A',memory_decision=group in 'CDE',
                stagnation_control=group in 'DE',route_search=group=='E')

def environment(method='A1'):
    if method not in METHODS:raise ValueError('Unknown arm')
    arm=HERE/'arms/common'
    env=dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join(map(str,[arm,arm/'bestfgs-project/src',arm/'hai-project/src',HERE,HERE/'upstream/harbor/src'])),
        HARBOR_TELEMETRY='0',HB_CONTINUE_MODE='same_conversation',HB_VERIFIER_FEEDBACK_MODE='binary',
        PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',LHTB_DISABLE_DISK_GUARD='1')
    env.pop('HB_PROCESS_REWARD',None)
    return env

def ordered_trials(manifest):
    for i,row in enumerate(manifest['tasks']):
        n=i%len(METHODS)
        order=METHODS[n:]+METHODS[:n]
        for arm in order:yield row,arm

def config(row,method,fixture=False):
    if method not in METHODS:raise ValueError('Unknown arm')
    task='fixture' if fixture else row['task']
    kwargs=dict(method='bestfgs',task_id=task,wall_seconds=240 if fixture else row['agent']['timeout_sec'],
        cpu=row['environment']['cpus'],memory_mb=row['environment']['memory_mb'],fixture='budget' if fixture else False,
        semantic_monitor=True,auto_memory=True,memory_reliability=True,monitor_reliability=True,
        outcome_reliability=True,stagnation_control=True,monitor_model=MODEL)
    kwargs.update(group_options(method[0]))
    return dict(job_name=('fixture-' if fixture else '')+method+'-'+task,
        jobs_dir=str(HERE/('fixtures' if fixture else 'runs')),n_attempts=1,n_concurrent_trials=1,
        retry={'max_retries':0},environment={'type':'docker','delete':True},
        agents=[dict(import_path='transport:TripleAgent',model_name=MODEL,override_setup_timeout_sec=600,kwargs=kwargs)],
        tasks=[dict(path=str(HERE/'fixture' if fixture else HERE/'upstream/tasks'/task))])

def plan():
    from harbor.models.job.config import JobConfig
    manifest=json.loads((HERE/'manifest.json').read_text())
    reference=json.loads((HERE/'raw-reference-manifest.json').read_text())
    if manifest['tasks']!=reference['tasks'] or manifest['methods']!=METHODS or manifest['total_trials']!=12:
        raise RuntimeError('Expected exactly the original twelve tasks and one frozen A arm')
    (HERE/'jobs').mkdir(exist_ok=True)
    for row,method in ordered_trials(manifest):
        if not fits([row]*PARALLEL_SLOTS,cpu_cap=32,memory_cap_mb=64*1024,max_slots=8):raise RuntimeError('Resource reservation does not fit')
        job=config(row,method);JobConfig.model_validate(job)
        write(HERE/'jobs'/(job['job_name']+'.json'),job)
    for method in METHODS:
        job=config(manifest['tasks'][0],method,True);JobConfig.model_validate(job)
        write(HERE/'jobs'/(job['job_name']+'.json'),job)
    print(json.dumps(dict(planned=12,groups=1,repetitions=1,slots=PARALLEL_SLOTS,model_calls=0)))

def verify_image(task):
    row=next(r for r in json.loads((HERE/'images.json').read_text()) if r['task']==task)
    info=json.loads(subprocess.check_output(['docker','image','inspect',row['image']]))[0]
    if info['Id']!=row['id'] or not any(x.endswith('@'+row['digest']) for x in info.get('RepoDigests',[])):
        raise RuntimeError('Official image identity changed: '+task)

def cleanup_owned(root):
    from docker_state import LABEL
    for path in root.glob('*/agent/host-state/owned.json'):
        record=json.loads(path.read_text())
        for ident in record['containers']:
            p=subprocess.run(['docker','inspect',ident],capture_output=True,text=True)
            if p.returncode:continue
            if (json.loads(p.stdout)[0]['Config'].get('Labels') or {}).get(LABEL)!=record['owner']:
                raise RuntimeError('Refusing cleanup of unowned container')
            subprocess.run(['docker','rm','-f',ident],capture_output=True,check=True)

def execute(row,method,fixture=False):
    if not fixture:reserve()
    if not fixture:validate();verify_image(row['task'])
    job=config(row,method,fixture)
    directory=Path(job['jobs_dir'])/job['job_name']
    if directory.exists():raise RuntimeError('Refusing replay of '+job['job_name'])
    command=[PYTHON,str(HERE/'harbor_entry.py'),'run','--config',str(HERE/'jobs'/(job['job_name']+'.json'))]
    wall=240 if fixture else row['agent']['timeout_sec']
    timeout=wall+600+(60 if fixture else row['verifier']['timeout_sec'])+300
    try:
        with (HERE/(job['job_name']+'.console.log')).open('x') as log:
            # Inherit the durable worker's owned process group so its outer
            # deadline also stops the Harbor child, not just the scheduler shim.
            process=subprocess.Popen(command,cwd=HERE,env=environment(method),stdout=log,stderr=subprocess.STDOUT)
            try:code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                raise RuntimeError('Host trial deadline exceeded')
        reports=list(directory.glob('*/result.json'))
        logs=list(directory.glob('*/agent/audit.jsonl'))
        if len(reports)!=1 or len(logs)!=1:raise RuntimeError('Missing/nonunique report or audit')
        report=json.loads(reports[0].read_text());events=[json.loads(s) for s in logs[0].read_text().splitlines()]
        result=dict(task=row['task'],method=method,algorithm='bestfgs',release=method,report=str(reports[0]),
            verifier_result=report.get('verifier_result'),exception_info=report.get('exception_info'),
            process_exit_code=code,audit_chain=verify(logs[0]))
        if fixture:
            reward=(report.get('verifier_result') or {}).get('rewards') or {}
            metadata=(report.get('agent_result') or {}).get('metadata') or {}
            if code or report.get('exception_info') or not reward or min(reward.values())<1 or metadata.get('continue_until_timeout_phases',0)<1:
                raise RuntimeError('Official continuation/isolation fixture failed')
        else:
            utilization=[e['utilization'] for e in events if e.get('event')=='mechanism_utilization']
            if len(utilization)!=1:raise RuntimeError('Missing/nonunique mechanism summary')
            result['mechanism_utilization']=utilization[0]
            endings=[e.get('result',{}) for e in events if e.get('event')=='method_end']
            result.update(group=method[0],repetition=int(method[1]),
                          model_usage=endings[-1].get('model_usage',{}) if endings else {},
                          wall_seconds=endings[-1].get('wall_seconds') if endings else None)
        return result
    finally:cleanup_owned(directory)

def source_hashes():
    paths=[p for p in HERE.iterdir() if p.is_file() and
           (p.suffix in ('.py','.ps1','.md') or p.name in
            ('manifest.json','prior-results.json','images.json','verified-digests.json','release-source-verification.json',
             'inventory.json','holdout-plan.json'))]
    for name in ('arms','upstream/harbor/src','jobs','fixture','tests'):
        paths.extend(p for p in (HERE/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts)
    for row in json.loads((HERE/'manifest.json').read_text())['tasks']:
        paths.extend(p for p in (HERE/'upstream/tasks'/row['task']).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for name in ('raw-reference-manifest.json','run-scope.json','frozen-source-verification.json'):
        paths.append(HERE/name)
    return {str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}

def validate():
    ready=json.loads((HERE/'ready.json').read_text())
    if ready.get('ready') is not True or ready.get('source_hashes')!=source_hashes():
        raise RuntimeError('Readiness gate incomplete or sealed inputs changed')
    return ready

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['plan','fixture','validate'])
    parser.add_argument('--method',choices=METHODS,default='A1');args=parser.parse_args()
    if args.mode=='plan':plan()
    elif args.mode=='validate':print(json.dumps(dict(ready=bool(validate()))))
    else:print(json.dumps(execute(json.loads((HERE/'manifest.json').read_text())['tasks'][0],args.method,True)))
