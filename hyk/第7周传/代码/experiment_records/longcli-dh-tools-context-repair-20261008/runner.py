"""Three incremental arms, one source, fresh task containers, shared role budgets."""
from dataclasses import replace
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from common import ROOT,save,sha,export_tree,validate
from docker_environment import DockerEnvironment,close_owned
from audit import Audit,JSONClientAudit
from shared_wire import SharedJSONWire
from budget_adapter import WireBudget,CheckedTransport,install_context_meter
from bestfgs.error_routing import RoutingPolicy
from bestfgs.code_tools import ToolTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.retrac_adapter import RetracModelConfig
from bestfgs.models import TaskSpec

CONSTRAINTS=(
 'Read INSTRUCTION.md; use only public requirements and public task files. Hidden grading runs after delivery.',
 'Work in /app; only /app files are delivered and checkpointed. /tmp and process state are not restored.',
 'Each command has a fresh shell; descendants are stopped after every command. Task network is disabled.',
 'Public verification and critic acceptance are not official task success.')

class Scripted:
    def __init__(self,values):self.values=iter(values)
    def complete_json(self,**kwargs):return next(self.values)
    def usage_summary(self):return {'model_calls':0,'api_requests':0,'prompt_tokens':0,'completion_tokens':0}

class LiveAudit(Audit):
    def __init__(self,path,health,directory,**kwargs):
        super().__init__(path,**kwargs);self.health=health;self.directory=directory
    def emit(self,event,**fields):
        super().emit(event,**fields)
        h=self.health;h.update(updated=time.time(),last_wire_event=event)
        if event=='wire_request':h['api_attempts']+=1
        if event=='wire_response' and fields.get('kind')=='ok':h['api_responses']+=1
        if event=='wire_rejected':h['last_wire_error']=fields.get('error_code')
        save(self.directory/'health.json',h)

class ObservedRunner(ToolTaskRunner):
    def _emit(self,event,**fields):
        super()._emit(event,**fields)
        self.health.update(updated=time.time(),last_event=event,tool_calls=self.counts['tool_calls'],
                           model_requests=self.counts['model_requests'])
        if event=='tool_attempt':self.health['tool_started']=time.time()
        if event=='tool_call':self.health['tool_finished']=time.time()
        if event=='infrastructure_error':self.health['engineering_fault']=fields.get('error_type','infrastructure_error')
        save(self.directory/'health.json',self.health)

def trial(row,key='',mock=False):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    install_context_meter()
    method=row['method'];job=method+'--'+row['task']
    if mock:job+='--'+str(time.time_ns())
    d=ROOT/('acceptance-jobs' if mock else 'jobs')/job;d.mkdir(parents=True,exist_ok=False)
    h={'job':job,'task':row['task'],'method':method,'pid':os.getpid(),'state':'preparing',
       'started':time.time(),'updated':time.time(),'api_attempts':0,'api_responses':0,'paid':not mock}
    save(d/'health.json',h);env=None;began=time.monotonic();budget=WireBudget(800)
    try:
        env=DockerEnvironment(row,d);deadline=began+(300 if mock else protocol['wall_seconds'])
        audit=LiveAudit(d/'model-audit.jsonl',h,d,secrets=(key,));clients={}
        policy=RoutingPolicy(**protocol['arms'][method])
        for role in ('action','advisor','monitor','critic'):
            cfg=RetracModelConfig(provider='deepseek',model_name=protocol['model'],
                api_key=key or 'keyless-fixture',base_url='https://api.deepseek.com',temperature=0,
                timeout_seconds=90,max_wall_time_seconds=180,request_attempts=1 if role=='monitor' else 2,
                parse_attempts=1,stream_response=False,thinking_enabled=False,max_tokens=protocol['max_tokens'])
            if mock:
                goal={'id':'G1','title':'Tool fixture','acceptance':'fixture value is two',
                    'depends_on':[],'targets':['dh-tool-fixture.py'],
                    'verification':{'argv':['python3','-c',
                        'from pathlib import Path;assert Path("dh-tool-fixture.py").read_text()=="value=2\\n";print("VERIFIED")'],
                        'stdout_contains':['VERIFIED']}}
                vals=([{'action':'run','argv':['python3','-c',
                            'from pathlib import Path;Path("dh-tool-fixture.py").write_text("value=1\\n")']},
                       {'action':'inspect_code','path':'dh-tool-fixture.py','subgoal_plan':[goal]},
                       {'action':'edit_code','path':'dh-tool-fixture.py','old_text':'value=1','new_text':'value=2'},
                       {'action':'verify_goal','goal_id':'G1'},
                       {'action':'submit','summary':'keyless acceptance only'}] if role=='action' else
                      [{'decision':'accept','requirements':['fixture output'], 'gaps':[],
                        'checks':[{'argv':['python3','-c','print("CRITIC_FIXTURE_OK")'],
                                   'stdout_contains':['CRITIC_FIXTURE_OK']}]},
                       {'decision':'accept','requirements':['fixture output'],'gaps':[],'checks':[]}] if role=='critic' else [])
                wire=Scripted(vals);wire.config=cfg
            else:
                wire=SharedJSONWire(cfg,audit,role,transport=CheckedTransport(audit));wire.budget=budget
            clients[role]=JSONClientAudit(wire,audit,role,deadline)
        config=LeanConfig(max_turns=800,max_tools=600,wall_seconds=max(1,deadline-time.monotonic()),
            command_seconds=300,semantic_monitor=True,auto_memory=True,memory_reliability=True,
            monitor_reliability=True,outcome_reliability=True,stagnation_control=False,route_search=False,
            contrastive_mode='orthogonal',contrastive_predictions=False,contrastive_threshold=.8,
            context_chars=protocol['context_limit'],subgoals_enabled=True)
        engine=ObservedRunner(env,clients['action'],clients['advisor'],config,d/'trace',secrets=(key,),
            monitor_client=clients['monitor'],routing=policy,critic_client=clients['critic'])
        engine.health=h;engine.directory=d;h['state']='running'
        result=engine.run(TaskSpec(row['task'],row['instruction'],constraints=CONSTRAINTS))
        save(d/'result.json',result)
        h.update(stop_reason=result['stop_reason'],submitted=result['submitted'],tool_calls=result['tool_calls'],
            model_requests=result['interaction_rounds'],model_usage=result['model_usage'],
            actual_api_attempts=budget.used,routing=result['routing'],error_type=result.get('error_type'))
        assert budget.used<=800 and result['tool_calls']<=600
        if result['stop_reason'] in {'infrastructure_error','credential_or_balance_error','delivery_error','context_budget_error'}:
            h['engineering_fault']=result['stop_reason']
        env.close();h['task_processes_stopped']=True
        h['artifact']=export_tree(env.workspace,d/'final-source.tar.gz',source_only=True)
        h['state']='engineering_failure' if h.get('engineering_fault') else ('keyless_pass' if mock else 'awaiting_grade')
        if mock:
            assert result['submitted'] and budget.used==0
            assert all(result['native_tools'].get(k+'_executed')==1 for k in
                       ('inspect_code','edit_code','verify_goal')),result
            assert result['subgoal_summary']['goals']['G1']['status']=='check_passed',result
    except Exception as error:
        import traceback
        h.update(state='engineering_failure',engineering_fault=type(error).__name__,
            error_frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name}
                          for f in traceback.extract_tb(error.__traceback__)[-8:]])
    finally:
        try:close_owned(d);h['task_processes_stopped']=True
        except Exception as error:h.update(state='engineering_failure',cleanup_error=type(error).__name__)
        h.update(ended=time.time(),updated=time.time(),seconds=time.monotonic()-began)
        save(d/'summary.json',h);save(d/'health.json',h)
    return h

def schedule(protocol):
    # Rotate arm ordering per question, fixed before any observed result.
    rows=[];methods=protocol['methods']
    for i,row in enumerate(protocol['tasks']):
        for method in methods[i%3:]+methods[:i%3]:rows.append(dict(row,method=method))
    return rows

def worker(key):
    protocol=validate();pending=schedule(protocol);active={};done=[];errors=[]
    ctx=multiprocessing.get_context('fork');fatal=None
    scratch=ROOT/'host-tmp';scratch.mkdir(exist_ok=True)
    os.environ['TMPDIR']=str(scratch)
    import tempfile
    tempfile.tempdir=str(scratch)
    with (ROOT/'grading-worker.log').open('x') as out,(ROOT/'grading-stderr.log').open('x') as err:
        grader=subprocess.Popen([sys.executable,'-B',str(ROOT/'grading_worker.py')],stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,start_new_session=True)
    save(ROOT/'grading-launch.json',{'pid':grader.pid,'model_calls':0})
    pilot_tasks={protocol['tasks'][0]['task']};pilot_done=set()
    try:
        while active or pending:
            if grader.poll() is not None:fatal='grading_worker_exited_early'
            gh=ROOT/'grading-health.json'
            if gh.exists() and json.loads(gh.read_text()).get('errors'):fatal='grading_failure'
            for job,(process,row,began) in list(active.items()):
                p=ROOT/'jobs'/job/'health.json';status=json.loads(p.read_text()) if p.exists() else {}
                fault=status.get('engineering_fault') or status.get('cleanup_error')
                if fault:fatal=fault
                if process.is_alive() and (time.time()-status.get('updated',began)>600 or time.time()-began>protocol['wall_seconds']+120):
                    os.kill(process.pid,signal.SIGKILL);process.join(2)
                    close_owned(ROOT/'jobs'/job)
                    status.update(state='engineering_failure',engineering_fault='watchdog_timeout',updated=time.time())
                    save(ROOT/'jobs'/job/'summary.json',status)
                    errors.append({'job':job,'reason':'watchdog_timeout'})
                if not process.is_alive():
                    process.join();summary_path=ROOT/'jobs'/job/'summary.json'
                    summary=json.loads(summary_path.read_text()) if summary_path.exists() else {}
                    if summary.get('state')=='awaiting_grade':
                        done.append(job)
                        if row['task'] in pilot_tasks:pilot_done.add(row['method'])
                    else:
                        errors.append({'job':job,'reason':summary.get('engineering_fault') or summary.get('stop_reason') or 'missing_summary'})
                        if summary.get('engineering_fault'):fatal=summary['engineering_fault']
                    active.pop(job)
            if fatal:break
            admitted=True
            while admitted and len(active)<protocol['concurrency'] and pending:
                admitted=False
                for i,row in enumerate(pending):
                    if len(pilot_done)<len(protocol['methods']) and row['task'] not in pilot_tasks:continue
                    running=sum(r['method']==row['method'] for _,r,_ in active.values())
                    if running>=protocol['concurrency_per_arm']:continue
                    pending.pop(i);job=row['method']+'--'+row['task']
                    process=ctx.Process(target=trial,args=(row,key));process.start()
                    active[job]=(process,row,time.time());admitted=True;break
            save(ROOT/'health.json',{'state':'running','pid':os.getpid(),'updated':time.time(),
                'active':list(active),'pending':[r['method']+'--'+r['task'] for r in pending],
                'completed':done,'errors':errors,'concurrency':protocol['concurrency'],
                'pilot_methods_complete':sorted(pilot_done)})
            time.sleep(3)
    except BaseException as error:
        fatal=type(error).__name__
    finally:
        if active:
            for job,(process,_,_) in active.items():
                if process.is_alive():os.kill(process.pid,signal.SIGSTOP)
            for job,(process,_,_) in active.items():
                if process.is_alive():os.kill(process.pid,signal.SIGKILL)
                process.join(2)
                try:close_owned(ROOT/'jobs'/job)
                except Exception as error:errors.append({'job':job,'reason':'cleanup_'+type(error).__name__})
                p=ROOT/'jobs'/job/'summary.json'
                if not p.exists():
                    hpath=ROOT/'jobs'/job/'health.json';s=json.loads(hpath.read_text()) if hpath.exists() else {}
                    s.update(state='interrupted',engineering_fault='shared_stop_'+str(fatal),updated=time.time())
                    save(p,s)
        save(ROOT/'health.json',{'state':'needs_attention' if fatal else 'generation_complete',
            'pid':os.getpid(),'updated':time.time(),'active':[],
            'pending':[r['method']+'--'+r['task'] for r in pending],
            'completed':done,'errors':errors,'fatal':fatal})
    if fatal:raise RuntimeError('Shared engineering fault; inspect public status')

if __name__=='__main__':raise SystemExit('Use launch.py with encrypted stdin')
