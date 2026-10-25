"""One ECS, 36 paired tasks, fail-closed protocol and resumable serial scheduling."""
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request

import toml
from harbor.models.job.config import JobConfig
from cloud_agent import common_args, CA_BUNDLE

ROOT = Path('/home/ecs-user/terminalbench-paired36-20260923')
CONTROL = ROOT/'control'
HERE = Path(__file__).resolve().parent
PROJECT = Path('/home/ecs-user/BestFGS-blocking-memory-v12')
PYTHON = '/home/ecs-user/terminalbench-runtime/venv/bin/python'
HARBOR = '/home/ecs-user/terminalbench-runtime/venv/bin/harbor'
UNIT = 'terminalbench-paired36'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, indent=2)+'\n')
    temp.replace(path)


def file_map(root):
    return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts}

def runtime_identity():
    return {'harbor':importlib.metadata.version('harbor'),
            'python':platform.python_version(),
            'docker':subprocess.check_output(['docker','--version'],text=True).strip()}


def freeze():
    original = json.loads((HERE/'deployed-source-hashes.json').read_text())
    for name, expected in original.items():
        if name.startswith('src/') and sha(PROJECT/name) != expected:
            raise RuntimeError('Algorithm source differs from the originally deployed frozen v12')
    for filename in ('paired-smoke-result.json','harness-smoke-result.json'):
        if not json.loads((HERE/filename).read_text()).get('passed'):
            raise RuntimeError('Shared synthetic end-to-end tests must pass first')
    selection = json.loads((CONTROL/'task-selection.json').read_text())
    readiness = json.loads((CONTROL/'image-readiness.json').read_text())
    if not readiness.get('completed') or readiness['selection_sha256'] != selection['selection_sha256']:
        raise RuntimeError('All 36 environments must pass preflight first')
    configdir = CONTROL/'jobs'
    configdir.mkdir(exist_ok=True)
    tasks, jobs = [], []
    for index, item in enumerate(selection['tasks']):
        ready = readiness['tasks'][item['id']]
        if not ready.get('ready') or ready.get('setup_version') != 'shared-python-ca-v2':
            raise RuntimeError('An environment is not ready')
        name = item['id'].split('/')[-1]
        original, pinned = Path(item['task_dir']), ROOT/'pinned-tasks'/name
        if sha(original/'task.toml') != item['public_config_sha256']:
            raise RuntimeError('Public task config changed after selection')
        if not pinned.exists():
            shutil.copytree(original, pinned)
            config = tomllib.loads((pinned/'task.toml').read_text())
            config['environment']['docker_image'] = ready['pinned_image']
            (pinned/'task.toml').write_text(toml.dumps(config))
        old, new = tomllib.loads((original/'task.toml').read_text()), tomllib.loads((pinned/'task.toml').read_text())
        new['environment']['docker_image'] = old['environment']['docker_image']
        if old != new:
            raise RuntimeError('Pinned task changed more than image identity')
        # Per-task environments/config/verifier are identical across both arms.
        tasks.append({'id':item['id'], 'path':str(pinned), 'pinned_image':ready['pinned_image'],
                      'source_files':file_map(original), 'pinned_files':file_map(pinned)})
        methods = ['bestfgs','raw'] if index % 2 == 0 else ['raw','bestfgs']
        for method in methods:
            jobname = f'{index:02d}-{name}-{method}'
            config = {'job_name':jobname,'jobs_dir':str(ROOT/'runs'),'n_attempts':1,
                      'n_concurrent_trials':1,'retry':{'max_retries':0},
                      'environment':{'type':'docker','delete':True},
                      'agents':[{'import_path':'cloud_agent:CloudAgent','model_name':'deepseek-flash',
                                 'extra_allowed_hosts':['api.deepseek.com'],
                                 'override_setup_timeout_sec':600,'kwargs':{'method':method}}],
                      'tasks':[{'path':str(pinned)}]}
            JobConfig.model_validate(config)
            path = configdir/(jobname+'.json')
            if path.exists() and json.loads(path.read_text()) != config:
                raise RuntimeError('Existing job configuration changed')
            atomic(path,config)
            jobs.append({'name':jobname,'id':item['id'],'method':method,'config':str(path),
                         'config_sha256':sha(path),
                         'watchdog_seconds':int(item['agent_timeout']+item['verifier_timeout']+1500)})
    protocol = {'version':'ecs-tb36-v12-1','selection_sha256':selection['selection_sha256'],
                'model':'deepseek-flash','api':'https://api.deepseek.com',
                'tasks':tasks,'jobs':jobs,'n_methods':2,'n_trials':72,
                'method_order':'alternating first method by position in frozen shuffled task list',
                'concurrency':1,'official_attempts_per_method_task':1,'whole_task_retries':0,
                'infra_guard':'pause on harness exception, unfinished result, low disk, credential error; never replay completed trials',
                'budgets':{'decision_turns':24,'cli_calls':80,'commands_per_decision':6,
                           'wall_time':'original task agent/verifier limits; common 40s delivery reserve',
                           'equal_token_budget':False},
                'args':{method:common_args('deepseek-flash',method) for method in ('bestfgs','raw')},
                'history':'actual chronological command/output history retained in both arms',
                'success':'official Harbor verifier reward == 1.0 without harness exception; raw reward retained; internal submit is not success',
                'metric_versions':['cli-comparison-v2','cli-metrics-report-v3','reusable-evidence-v1'],
                'redundancy':'detected reusable-evidence calls / all actual CLI calls; unknown count reported; not a causal savings claim',
                'rounds':'actual CLI feedback batches; decision turns and model requests reported separately',
                'snapshot_scope':'/app task workspace only; service/OS state outside it is not rolled back',
                'source_files':file_map(PROJECT/'src'),
                'runtime':runtime_identity(),
                'agent_ca_bundle_sha256':sha(CA_BUNDLE),
                'control_files':{name:sha(HERE/name) for name in ('cloud_agent.py','container_runner.py','paired_control.py')},
                'credential_policy':'key entered only at launch; root-only volatile /run systemd credential; never in job JSON',
                'telemetry':False,'formal_calls_started':False}
    wrapped = {'protocol':protocol,'protocol_sha256':digest(protocol)}
    path = CONTROL/'protocol.json'
    if path.exists() and json.loads(path.read_text()) != wrapped:
        raise RuntimeError('Protocol is frozen; refusing change')
    atomic(path,wrapped)
    print(json.dumps({'ready_for_key':True,'tasks':36,'trials':72,'protocol_sha256':wrapped['protocol_sha256']}))


def validate():
    wrapped = json.loads((CONTROL/'protocol.json').read_text())
    p = wrapped['protocol']
    if digest(p) != wrapped['protocol_sha256'] or file_map(PROJECT/'src') != p['source_files']:
        raise RuntimeError('Frozen protocol or algorithm identity mismatch')
    if sha(CA_BUNDLE) != p['agent_ca_bundle_sha256']:
        raise RuntimeError('Agent CA bundle changed')
    if runtime_identity() != p['runtime']:
        raise RuntimeError('Frozen execution runtime changed')
    for name, expected in p['control_files'].items():
        if sha(HERE/name) != expected:
            raise RuntimeError('Frozen transport identity mismatch')
    for task in p['tasks']:
        if file_map(Path(task['path'])) != task['pinned_files']:
            raise RuntimeError('Task or verifier changed')
    for job in p['jobs']:
        if sha(job['config']) != job['config_sha256']:
            raise RuntimeError('Job configuration changed')
    return wrapped


def status():
    paths = {'preparation':CONTROL/'image-readiness.json','worker':ROOT/'health.json','report':ROOT/'summary.json'}
    result = {}
    for name, path in paths.items():
        if path.exists():
            data = json.loads(path.read_text())
            if name == 'preparation':
                data = {'ready':sum(bool(x.get('ready')) and x.get('setup_version') == 'shared-python-ca-v2' for x in data['tasks'].values()),'total':36,
                        'complete':data.get('completed'), 'current':data.get('current')}
            result[name] = data
    result['ready_for_key'] = False
    if (CONTROL/'protocol.json').is_file():
        result['protocol_sha256'] = validate()['protocol_sha256']
        result['ready_for_key'] = True
    print(json.dumps(result,indent=2))


def start():
    lock = (CONTROL/'start.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    validate()
    if subprocess.run(['systemctl','is-active','--quiet',UNIT]).returncode == 0:
        raise RuntimeError('Worker is already active; do not duplicate')
    if (ROOT/'health.json').exists() and json.loads((ROOT/'health.json').read_text()).get('state') == 'completed':
        raise RuntimeError('Experiment already completed; no automatic rerun')
    key = sys.stdin.readline().strip()
    if not key or any(c.isspace() for c in key):
        raise RuntimeError('Missing or malformed key')
    request = urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            models = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Authentication check HTTP {error.code}; credentials not logged') from None
    if 'deepseek-flash' not in {m['id'] for m in models.get('data',[])}:
        raise RuntimeError('Frozen model not present in account model list; refusing substitution')
    cred = Path('/run/terminalbench-paired36')
    cred.mkdir(mode=0o700,exist_ok=True)
    path = cred/'deepseek_api_key'
    fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write(key)
    key = ''
    try:
        subprocess.run(['systemd-run','--unit='+UNIT,'--collect',
                        '--property=WorkingDirectory='+str(HERE),'--property=Type=exec',
                        '--property=LoadCredential=deepseek_api_key:'+str(path),
                        '--property=KillMode=control-group','--property=TimeoutStopSec=40',
                        '--setenv=HARBOR_TELEMETRY=0','--setenv=PYTHONUNBUFFERED=1',
                        PYTHON,str(HERE/'paired_control.py'),'run'],check=True)
    finally:
        path.unlink(missing_ok=True)
    print('Cloud paired worker launched; secret is in volatile systemd credential storage only.')


def trial_results(job):
    paths = list((ROOT/'runs'/job['name']).glob('*/result.json'))
    results = []
    for path in paths:
        value = json.loads(path.read_text())
        if 'task_name' in value and value.get('finished_at'):
            results.append(path)
    return results


def report(protocol):
    rows = []
    for job in protocol['jobs']:
        row = {'id':job['id'],'method':job['method'],'state':'not_started','success':None,
               'interaction_rounds':None,'decision_turns':None,'tool_calls':None,'redundant_tool_calls':None,'unknown_calls':None}
        paths = trial_results(job)
        if len(paths) == 1:
            result = json.loads(paths[0].read_text())
            exception = result.get('exception_info')
            rewards = (result.get('verifier_result') or {}).get('rewards') or {}
            row.update(state='error' if exception else 'completed', exception_type=(exception or {}).get('exception_type'),
                       official_reward=rewards.get('reward'),
                       success=(float(rewards['reward'])==1.0) if not exception and 'reward' in rewards else None)
            checkpoint = paths[0].parent/'agent/runtime/search_checkpoint.json'
            if checkpoint.exists():
                data = json.loads(checkpoint.read_text())
                metrics = data.get('comparison_metrics') or {}
                row.update(interaction_rounds=metrics.get('interaction_rounds'),decision_turns=data.get('decision_turns'),
                           tool_calls=metrics.get('tool_calls'),redundant_tool_calls=metrics.get('redundant_tool_calls'),
                           unknown_calls=metrics.get('redundancy_unknown_calls'),trace_complete=metrics.get('trace_complete'),
                           model_usage=data.get('model_usage'),blocking_memory_metrics=data.get('blocking_memory_metrics'))
        rows.append(row)
    summaries = {}
    for method in ('bestfgs','raw'):
        selected = [r for r in rows if r['method']==method]
        measured = [r for r in selected if r['interaction_rounds'] is not None and r.get('trace_complete')]
        calls = sum(r['tool_calls'] for r in measured)
        summaries[method] = {'expected':36,'scored':sum(r['success'] is not None for r in selected),
            'successes':sum(r['success'] is True for r in selected),
            'official_success_rate':sum(r['success'] is True for r in selected)/36 if all(r['success'] is not None for r in selected) else None,
            'errors':sum(r['state']=='error' for r in selected),'complete_metric_traces':len(measured),
            'mean_interaction_rounds':sum(r['interaction_rounds'] for r in measured)/36 if len(measured)==36 else None,
            'detected_redundancy_rate':sum(r['redundant_tool_calls'] for r in measured)/calls if calls and len(measured)==36 else None,
            'partial_measured_tool_calls':calls,'partial_unknown_calls':sum(r['unknown_calls'] or 0 for r in measured)}
    atomic(ROOT/'summary.json',{'groups':summaries,'rows':rows})


def run():
    lock = (ROOT/'worker.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    wrapped = validate()
    keypath = Path(os.environ['CREDENTIALS_DIRECTORY'])/'deepseek_api_key'
    env = dict(os.environ,DEEPSEEK_API_KEY=keypath.read_text().strip(),HARBOR_TELEMETRY='0',PYTHONPATH=str(HERE),
               HTTP_PROXY='http://127.0.0.1:28761',HTTPS_PROXY='http://127.0.0.1:28761',
               NO_PROXY='localhost,127.0.0.1,::1,api.deepseek.com')
    state = {'state':'running','protocol_sha256':wrapped['protocol_sha256'],'pid':os.getpid(),'completed':0,'total':72}
    stop = threading.Event()
    def heartbeat():
        while not stop.is_set():
            atomic(ROOT/'health.json',{**state,'heartbeat':time.time()})
            stop.wait(20)
    thread = threading.Thread(target=heartbeat,daemon=True)
    thread.start()
    try:
        for job in wrapped['protocol']['jobs']:
            if len(trial_results(job))==1:
                state['completed'] += 1
                continue
            directory = ROOT/'runs'/job['name']
            if directory.exists():
                raise RuntimeError('Interrupted trial without final result: stop instead of paying for a duplicate')
            validate()
            if shutil.disk_usage(ROOT).free < 20*1024**3:
                raise RuntimeError('Disk guard: below 20 GiB free')
            state.update(current=job['name'],job_started=time.time())
            with (ROOT/(job['name']+'.console.log')).open('x') as log:
                process = subprocess.Popen([HARBOR,'run','--config',job['config']],cwd=HERE,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                state['child_pid'] = process.pid
                try:
                    deadline = time.monotonic()+job['watchdog_seconds']
                    while process.poll() is None:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Hard watchdog timeout')
                        if shutil.disk_usage(ROOT).free < 20*1024**3:
                            raise RuntimeError('Disk guard during active task: below 20 GiB free')
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            pass
                    code = process.returncode
                except RuntimeError:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL)
                        process.wait()
                    raise
            if len(trial_results(job)) != 1:
                raise RuntimeError(f'Job has no unique final trial result (exit {code}); paused')
            state['completed'] += 1
            report(wrapped['protocol'])
            trial = json.loads(trial_results(job)[0].read_text())
            if trial.get('exception_info'):
                raise RuntimeError('Official harness exception: paused; inspect it before continuing, no automatic replay')
            checkpoint = trial_results(job)[0].parent/'agent/runtime/search_checkpoint.json'
            if checkpoint.exists():
                usage = json.loads(checkpoint.read_text()).get('model_usage') or {}
                if usage.get('last_failure_detail') in {'http_401','http_402','http_403','http_404'}:
                    raise RuntimeError('Credential/balance/model API error: paused before spending on more tasks')
        state.update(state='completed',current=None,child_pid=None)
    except Exception as error:
        state.update(state='needs_attention',error=str(error))
        raise
    finally:
        stop.set()
        thread.join()
        atomic(ROOT/'health.json',{**state,'heartbeat':time.time()})
        report(wrapped['protocol'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['freeze','validate','status','start','run','report'])
    args = parser.parse_args()
    if args.action=='validate':
        print(json.dumps({'valid':True,'protocol_sha256':validate()['protocol_sha256']}))
    elif args.action=='report':
        report(validate()['protocol'])
        status()
    else:
        globals()[args.action]()
