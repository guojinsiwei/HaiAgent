"""Historical best DH, DSH-large resource envelope, isolated 20-task campaign."""
from dataclasses import replace
import argparse
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from common import ROOT,save,export_tree,sha
from docker_environment import DockerEnvironment,close_owned
from historical_runner import lean_config,CONSTRAINTS,ScriptedJSON
from audit import Audit,JSONClientAudit
from shared_wire import SharedJSONWire
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.retrac_adapter import RetracModelConfig
from bestfgs.models import TaskSpec
from budget_adapter import install_context_meter,WireBudget,CheckedTransport

CONSTRAINTS=tuple(c.replace('Each command has a fresh process namespace; background services do not persist.',
    'Each command has a fresh shell; background child processes are stopped after every command.') for c in CONSTRAINTS)

FAULT_STOPS={'infrastructure_error','delivery_error','model_error','credential_or_balance_error',
             'model_or_protocol_error_limit','protocol_error'}
TASK_LOCAL_STOPS={'delivery_error','model_error','model_or_protocol_error_limit','protocol_error'}
SHARED_FATAL_STOPS={'infrastructure_error','credential_or_balance_error'}

def validate_ready():
    ready=json.loads((ROOT/'acceptance.json').read_text())
    assert ready['state']=='passed' and ready['paid_model_calls']==0
    grading=json.loads((ROOT/'grading-acceptance.json').read_text())
    assert grading['state']=='passed' and grading['container_destroyed']
    repair_path=ROOT/'task-isolation-repair.json'
    repairs={}
    if repair_path.exists():
        repair=json.loads(repair_path.read_text())
        assert repair['state']=='passed' and repair['paid_model_calls']==0
        assert repair['base_acceptance_sha256']==sha(ROOT/'acceptance.json')
        repairs=repair['hashes']
        assert set(repairs)=={'runner.py','grading_worker.py','test_controller.py'}
        assert repair['original_hashes']=={name:ready['hashes'][name] for name in repairs}
        assert repair['checks']['controller_model_calls']==0
    for name,expected in ready['hashes'].items():
        assert sha(ROOT/name)==repairs.get(name,expected),'Sealed code changed: '+name
    return json.loads((ROOT/'protocol.json').read_text())

class LiveAudit(Audit):
    def __init__(self,path,health,directory,**kwargs):
        super().__init__(path,**kwargs);self.health=health;self.directory=directory
    def emit(self,event,**fields):
        super().emit(event,**fields)
        h=self.health;h['updated']=time.time();h['last_event']=event
        if event=='wire_request':h['api_attempts']=h.get('api_attempts',0)+1
        if event=='wire_response' and fields.get('kind')=='ok':h['api_responses']=h.get('api_responses',0)+1
        if event=='wire_rejected':
            h['wire_rejections']=h.get('wire_rejections',0)+1
            h['last_wire_error']=fields.get('error_code')
        save(self.directory/'health.json',h)

class ObservedRunner(LeanTaskRunner):
    def _emit(self,event,**fields):
        super()._emit(event,**fields)
        self.health.update(updated=time.time(),last_native_event=event,
            tool_calls=self.counts.get('tool_calls',0),model_requests=self.counts.get('model_requests',0))
        if event=='tool_attempt':self.health['tool_started']=time.time()
        if event=='tool_call':self.health['tool_finished']=time.time()
        if event in ('infrastructure_error','delivery_error'):self.health['engineering_fault']=event
        save(self.directory/'health.json',self.health)

def run_trial(row,key='',mock=False):
    if mock:key='keyless-fixture-not-a-credential'
    install_context_meter()
    protocol=json.loads((ROOT/'protocol.json').read_text())
    job=('keyless' if mock else 'dh')+'--'+row['task']
    if mock:job+='--'+str(time.time_ns())
    d=ROOT/('acceptance-jobs' if mock else 'jobs')/job;d.mkdir(parents=True,exist_ok=False)
    h=dict(job=job,task=row['task'],method='dh',state='preparing',started=time.time(),updated=time.time(),
           api_attempts=0,api_responses=0,paid=not mock,pid=os.getpid())
    save(d/'health.json',h);env=None;start=time.monotonic();budget=WireBudget(800)
    try:
        env=DockerEnvironment(row,d)
        h.update(state='running',updated=time.time())
        audit=LiveAudit(d/'model-audit.jsonl',h,d,secrets=(key,))
        deadline=start+(300 if mock else 7200)
        commands=[dict(action='run',argv=['sh','-c','cat INSTRUCTION.md >/dev/null; printf fixture-ok'],purpose='fixture'),
                  dict(action='submit',summary='Keyless fixture only')]
        clients={}
        for role in ('action','advisor','monitor'):
            cfg=RetracModelConfig(provider='deepseek',model_name=protocol['model'],base_url='https://api.deepseek.com',
                api_key=key,temperature=0,timeout_seconds=90,max_wall_time_seconds=180,
                request_attempts=1 if role=='monitor' else 2,parse_attempts=1,
                stream_response=False,thinking_enabled=False,max_tokens=32768)
            if mock:wire=ScriptedJSON(commands if role=='action' else []);wire.config=cfg
            else:
                wire=SharedJSONWire(cfg,audit,role,transport=CheckedTransport(audit));wire.budget=budget
            clients[role]=JSONClientAudit(wire,audit,role,deadline)
        config=lean_config(dict(protocol,wall_seconds=max(1,deadline-time.monotonic())),'dh')
        engine=ObservedRunner(env,clients['action'],clients['advisor'],config,d/'trace',
                              secrets=(key,),monitor_client=clients['monitor'])
        engine.health=h;engine.directory=d
        result=engine.run(TaskSpec(row['task'],row['instruction'],constraints=CONSTRAINTS))
        save(d/'result.json',result)
        h.update(stop_reason=result['stop_reason'],tool_calls=result['tool_calls'],
                 model_requests=result['interaction_rounds'],model_usage=result['model_usage'],
                 actual_api_attempts=budget.used,submitted=result['submitted'])
        assert budget.used<=800 and result['tool_calls']<=600
        if result['stop_reason'] in FAULT_STOPS:h['engineering_fault']=result['stop_reason']
        save(d/'health.json',h)
        env.close();h['task_processes_stopped']=True
        h['artifact']=export_tree(env.workspace,d/'final-source.tar.gz',source_only=True)
        h['state']='engineering_failure' if h.get('engineering_fault') else ('keyless_pass' if mock else 'awaiting_grade')
        if mock:assert result['submitted'] and result['tool_calls']==1 and budget.used==0
    except Exception as exc:
        h.update(state='engineering_failure',engineering_fault=type(exc).__name__)
        # No exception bodies: a provider or model string could contain credentials.
        import traceback
        h['error_frames']=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name}
                           for f in traceback.extract_tb(exc.__traceback__)[-8:]]
    finally:
        try:close_owned(d);h['task_processes_stopped']=True
        except Exception as exc:h.update(state='engineering_failure',cleanup_error=type(exc).__name__)
        h.update(ended=time.time(),seconds=time.monotonic()-start,updated=time.time())
        save(d/'summary.json',h);save(d/'health.json',h)
    return h

ACTIVE_PROCESSES={}

def worker(key):
    scratch=ROOT/'host-tmp';scratch.mkdir(exist_ok=True)
    os.environ['TMPDIR']=str(scratch)
    import tempfile
    tempfile.tempdir=str(scratch)
    try:return _worker(key)
    except BaseException as exc:
        # Even a controller exception must not leave paid child tasks orphaned.
        for process,_,_ in ACTIVE_PROCESSES.values():
            if process.is_alive():
                try:os.kill(process.pid,signal.SIGSTOP)
                except ProcessLookupError:pass
        for process,_,_ in ACTIVE_PROCESSES.values():
            if process.is_alive():
                try:os.kill(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            process.join(1)
        cleanup_errors=[]
        for task in ACTIVE_PROCESSES:
            try:close_owned(ROOT/'jobs'/('dh--'+task))
            except Exception as error:cleanup_errors.append({'task':task,'error_type':type(error).__name__})
        save(ROOT/'health.json',{'state':'needs_attention','active':[],'updated':time.time(),
            'errors':[{'reason':'controller_'+type(exc).__name__}], 'cleanup_errors':cleanup_errors})
        raise

def _worker(key):
    protocol=validate_ready();pending=list(protocol['tasks']);active={};done=[];errors=[];fatal_errors=[]
    global ACTIVE_PROCESSES
    ACTIVE_PROCESSES=active
    ctx=multiprocessing.get_context('fork')
    h=dict(state='running',pid=os.getpid(),started=time.time(),completed=done,errors=errors,
           fatal_errors=fatal_errors,
           first_pilot=protocol['tasks'][0]['task'],concurrency=4)
    with (ROOT/'grading-worker.log').open('x') as out,(ROOT/'grading-stderr.log').open('x') as err:
        grader=subprocess.Popen([sys.executable,'-B',str(ROOT/'grading_worker.py')],stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,start_new_session=True)
    save(ROOT/'grading-launch.json',{'pid':grader.pid,'model_calls':0})
    while active or pending:
        ghpath=ROOT/'grading-health.json'
        if ghpath.exists() and json.loads(ghpath.read_text()).get('errors'):
            fatal_errors.append({'task':'grader','reason':'grading_failure'})
        if grader.poll() is not None and not fatal_errors:
            fatal_errors.append({'task':'grader','reason':'grading_worker_exited_early'})
        for task,(process,row,began) in list(active.items()):
            d=ROOT/'jobs'/('dh--'+task);hp=d/'health.json'
            status=json.loads(hp.read_text()) if hp.exists() else {}
            fault=status.get('engineering_fault') or status.get('cleanup_error')
            if process.is_alive():
                if status.get('cleanup_error') or fault in SHARED_FATAL_STOPS:
                    fatal_errors.append({'task':task,'reason':status.get('cleanup_error') or fault})
                elif time.time()-status.get('updated',began)>600 or time.time()-began>7320:
                    # A stuck trial is local: stop and clean up only its owned container.
                    try:os.kill(process.pid,signal.SIGSTOP)
                    except ProcessLookupError:pass
                    try:os.kill(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.join(1)
                    if process.is_alive():
                        fatal_errors.append({'task':task,'reason':'task_kill_failed'})
                        continue
                    try:close_owned(d)
                    except Exception as exc:
                        fatal_errors.append({'task':task,'reason':'cleanup_'+type(exc).__name__})
                    save(d/'interruption.json',{'state':'task_failed','reason':'stalled_or_wall_overrun','time':time.time()})
                    errors.append({'task':task,'reason':'stalled_or_wall_overrun'})
                    del active[task]
                continue
            else:
                process.join(1)
                summary=json.loads((d/'summary.json').read_text()) if (d/'summary.json').exists() else {}
                reason=summary.get('engineering_fault') or summary.get('cleanup_error') or 'missing_valid_summary'
                if summary.get('state')=='awaiting_grade':done.append(task)
                elif reason in TASK_LOCAL_STOPS:
                    errors.append({'task':task,'reason':reason})
                else:fatal_errors.append({'task':task,'reason':reason})
                del active[task]
        if fatal_errors:
            h.update(state='stopping_engineering_failure',active=list(active),pending=[r['task'] for r in pending],updated=time.time())
            save(ROOT/'health.json',h)
            for p,_,_ in active.values():
                if p.is_alive():
                    try:os.kill(p.pid,signal.SIGSTOP)
                    except ProcessLookupError:pass
            for p,_,_ in active.values():
                if p.is_alive():
                    try:os.kill(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                p.join(1)
            for task,(p,row,_) in active.items():
                d=ROOT/'jobs'/('dh--'+task)
                try:close_owned(d)
                except Exception as exc:fatal_errors.append({'task':task,'reason':'cleanup_'+type(exc).__name__})
                # Preserve interrupted workspaces and logs. Do not grade as completed or auto-retry.
                save(d/'interruption.json',{'state':'stopped_with_batch','time':time.time(),'root_errors':fatal_errors[:]})
            active.clear();break
        capacity=4 if done or errors else 1
        while pending and len(active)<capacity:
            row=pending.pop(0);p=ctx.Process(target=run_trial,args=(row,key));p.start()
            active[row['task']]=(p,row,time.time())
        h.update(state='running_with_task_errors' if errors else 'running',updated=time.time(),
                 active=list(active),pending=[r['task'] for r in pending],completed=done,
                 errors=errors,fatal_errors=fatal_errors)
        save(ROOT/'health.json',h)
        time.sleep(3)
    h.update(state='needs_attention' if fatal_errors else
             'generation_complete_with_task_errors' if errors else 'generation_complete',
             active=[],pending=[r['task'] for r in pending],updated=time.time(),
             errors=errors,fatal_errors=fatal_errors)
    save(ROOT/'health.json',h)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--credential-file');args=parser.parse_args()
    path=Path(args.credential_file)
    try:key=path.read_text().strip()
    finally:path.unlink(missing_ok=True)
    worker(key)
