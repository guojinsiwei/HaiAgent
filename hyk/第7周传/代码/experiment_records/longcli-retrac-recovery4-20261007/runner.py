"""Four academy Docker trials; untouched recursive engine, immutable artifacts."""
from dataclasses import asdict
import json
import multiprocessing
import os
from pathlib import Path
import resource
import secrets
import signal
import sys
import time
from common import ROOT,save,export_tree
from docker_terminal import PersistentTerminal,cleanup_owned
sys.path.insert(0,str(ROOT/'retrac/src'))
from retrac.audit import JsonlLogger,redact
from retrac.engine import RetracConfig
from matched_adapter import MatchedClient,MatchedRunner
from fault_guard import failure,event_failure,canary_passed
from process_receipt import reconcile

class ProgressLogger(JsonlLogger):
    def __init__(self,directory,health,summary,**kwargs):
        super().__init__(directory,**kwargs);self.health=health;self.summary=summary
        self.models=self.tools=self.states=0
    def write(self,event,**payload):
        super().write(event,**payload)
        if event=='model_request':self.models+=1
        if event=='command':self.tools+=1
        if event=='compressed_state':self.states+=1
        fault=event_failure(event,payload)
        if fault:self.summary['engineering_fault']=fault
        self.summary.update(updated=time.time(),model_calls=self.models,root_tool_dispatches=self.tools,
                            committed_states=self.states,round=payload.get('round',self.summary.get('round')))
        save(self.health,self.summary)

def run_trial(row,cpus,key=None,mock=False,pressure=False,suffix=''):
    os.setsid()
    def stop(_s,_f):raise RuntimeError('Controller deadline reached')
    signal.signal(signal.SIGTERM,stop)
    job=('keyless' if mock else 'retrac')+'--'+row['task']+suffix
    d=ROOT/('acceptance-jobs' if mock else 'jobs')/job;d.mkdir(parents=True,exist_ok=False)
    h={'job':job,'task':row['task'],'pid':os.getpid(),'state':'preparing','started':time.time(),'paid':not mock,
       'fresh_container':True,'fresh_home':True,'api_key_visible_in_task':False}
    save(d/'health.json',h);terminal=None
    try:
        os.sched_setaffinity(0,cpus)
        resource.setrlimit(resource.RLIMIT_AS,(3*2**30,3*2**30))
        logger=ProgressLogger(d/'trace',d/'health.json',h,secrets=(key,))
        client=MatchedClient(key,d/'api',mock,pressure,'EARLY_FACT_'+secrets.token_hex(12))
        config=RetracConfig(rounds=8,max_steps_per_round=50,max_tool_calls=600,max_model_calls=800,
            max_total_seconds=360 if mock else row['wall_seconds'],max_context_chars=48000,
            compression_reserve_chars=12000,max_observation_chars=24000,max_state_chars=8000,
            max_command_duration=300,max_parse_attempts=2,summary_variant='full')
        terminal=PersistentTerminal(row,d,cpus,logger,job)
        h['writable_workspace_verified']=terminal.writable_workspace_verified
        if mock:
            terminal.observe();terminal.execute('sleep 10\n',0.3);terminal.execute('C-c',0.3)
            assert 'CONTROL_OK' in terminal.execute("printf 'CONTROL_OK\\n'\n",1)
            # Heredoc, newline, cwd and empty-poll semantics, before the engine.
            output=terminal.execute("mkdir -p /app/fixture-sub; cd /app/fixture-sub; python3 - <<'PY'\nprint('HEREDOC_OK')\nPY\n",1)
            assert 'HEREDOC_OK' in output
            terminal.execute('cd /app\n',0.3);terminal.execute('',0.1)
        h.update(state='running',updated=time.time(),solving_started=time.time(),cpu_affinity=cpus,configuration=asdict(config))
        save(d/'health.json',h)
        instruction='Run the keyless continuity test.' if mock else row['instruction']
        instruction+='\nWork in /app; only /app files are delivered. Hidden tests and external task networking are unavailable. '
        instruction+='Budgets: 800 model requests including compression/format repair, 600 terminal calls, 4096 output tokens per request, 48000 UTF-8 input bytes.'
        result=MatchedRunner(client,config,logger).run(instruction,terminal)
        save(d/'result.json',redact(asdict(result),secrets=(key,)))
        h.update(stop_reason=result.stop_reason,error=redact(result.error,secrets=(key,)))
        fault=failure(h)
        if fault:h['engineering_fault']=fault
        save(d/'health.json',h)  # Publish failure BEFORE potentially slow source export.
        terminal.close()
        h.update(stop_reason=result.stop_reason,error=redact(result.error,secrets=(key,)),
                 logical_model_requests=result.model_calls,model_calls=result.model_calls,
                 root_tool_dispatches=result.tool_calls,api_attempts=client.wire_attempts,
                 input_tokens=result.input_tokens,output_tokens=result.output_tokens,
                 rounds=len(result.rounds),round_details=[asdict(r) for r in result.rounds],task_processes_stopped=True)
        save(d/'result.json',redact(asdict(result),secrets=(key,)))
        if mock:
            assert result.stop_reason=='rounds_completed' and not result.error and len(result.rounds)==8
            assert len([r for r in result.rounds if r.state])==7
            assert (terminal.app/'continuity-proof.txt').read_text().strip()==client.fact
            events=[json.loads(line) for line in (d/'trace/events.jsonl').read_text().splitlines()]
            assert any('ISOLATION_OK' in e.get('output','') and client.fact in e.get('output','') for e in events if e['event']=='tool_result')
            from context_limit import input_bytes
            calls=[json.loads(p.read_text()) for p in (d/'api').glob('mock-request-*.json')]
            assert all(input_bytes({'messages':r['messages']})<=48000 for r in calls)
            h.update(state='keyless_pass',maximum_input_bytes=max(input_bytes({'messages':r['messages']}) for r in calls),
                     persistent_terminal_verified=True,recursive_memory_verified=True)
        else:
            contexts=[json.loads(p.read_text()) for p in (d/'api').glob('context-*.json')]
            h.update(state='awaiting_grade',maximum_input_bytes=max((c['after_bytes'] for c in contexts),default=0),
                     artifact=export_tree(terminal.app,d/'final-source.tar.gz',source_only=True))
    except Exception as exc:
        details=redact(str(exc),secrets=(key,))[:700]
        if h.get('error'):h['secondary_controller_error']=details
        else:h['error']=details
        h.update(state='engineering_failure',error_type=type(exc).__name__,updated=time.time())
        save(d/'health.json',h)
    finally:
        try:
            if terminal:terminal.close()
            elif (d/'container.json').exists():
                receipt=json.loads((d/'container.json').read_text());cleanup_owned(receipt['name'],job)
            h['task_processes_stopped']=True
        except Exception as exc:
            h.update(cleanup_error=type(exc).__name__,task_processes_stopped=bool(getattr(exc,'cleanup_receipt',{}).get('stopped')))
            if getattr(exc,'cleanup_receipt',None):h['cleanup_receipt']=exc.cleanup_receipt
        h.update(ended=time.time(),seconds=time.time()-h['started']);save(d/'summary.json',h);save(d/'health.json',h)
    return h

def terminate_trial(p):
    if not p.is_alive():return
    try:
        os.kill(p.pid,signal.SIGSTOP)
        os.kill(p.pid,signal.SIGKILL)
    except ProcessLookupError:return
    p.join(1)
    assert not p.is_alive(),'Child stop could not be confirmed'


ACTIVE_PROCESSES={}

def worker(key,trial_function=None,test_tasks=None):
    global ACTIVE_PROCESSES
    try:return _worker(key,trial_function,test_tasks)
    except BaseException as error:
        # A controller exception must not leave active paid tasks orphaned.
        for p,_,_ in ACTIVE_PROCESSES.values():
            if p.is_alive():
                try:os.kill(p.pid,signal.SIGSTOP)
                except ProcessLookupError:pass
        for p,_,_ in ACTIVE_PROCESSES.values():
            if p.is_alive():
                try:os.kill(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            p.join(1)
        cleanup_errors=[]
        for p,row,_ in ACTIVE_PROCESSES.values():
            d=ROOT/'jobs'/('retrac--'+row['task']);f=d/'container.json'
            if not f.exists():continue
            try:
                c=json.loads(f.read_text());cleanup_owned(c['name'],c['job'])
            except Exception as exc:cleanup_errors.append({'task':row['task'],'error_type':type(exc).__name__})
        save(ROOT/'health.json',{'state':'needs_attention','updated':time.time(),
            'errors':[{'task':'controller','reason':type(error).__name__}],
            'active':[],'cleanup_errors':cleanup_errors,'model_calls':0})
        raise

def _worker(key,trial_function=None,test_tasks=None):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    tasks=list(test_tasks if test_tasks is not None else (protocol.get('run_tasks') or protocol['tasks']))
    canary_names=protocol['engineering_guard']['canary_tasks']
    canaries=[r for name in canary_names for r in tasks if r['task']==name]
    assert len(canaries)==len(canary_names)
    pending=canaries+[r for r in tasks if r['task'] not in canary_names]
    active={};done=[];errors=[];ctx=multiprocessing.get_context('fork')
    global ACTIVE_PROCESSES
    ACTIVE_PROCESSES=active
    trial_function=trial_function or run_trial
    h={'state':'running','pid':os.getpid(),'completed':done,'errors':errors,
        'canary_state':'passed' if not canary_names else 'pending','engineering_fail_fast':True}
    def add_error(task,reason):
        if not any(e['task']==task and e['reason']==reason for e in errors):
            errors.append({'task':task,'reason':reason,'new_admission_stopped':True})
    while pending or active:
        grader=ROOT/'grading-launch.json'
        if grader.exists():
            gpid=json.loads(grader.read_text())['pid'];gproc=Path('/proc')/str(gpid)/'stat'
            if not gproc.exists() or gproc.read_text().rsplit(')',1)[1].split()[0]=='Z':
                add_error('grader','grading_worker_exited_before_generation_complete')
        ghealth=ROOT/'grading-health.json'
        if ghealth.exists():
            gh=json.loads(ghealth.read_text())
            if gh.get('errors'):add_error('grader','official_grading_failed')
            if gh.get('state')=='grading' and time.time()-gh.get('updated',time.time())>1500:
                add_error('grader','grading_heartbeat_stale')
        # Inspect BEFORE new admission. Fatal health/events are live, not just final state.
        for slot,(p,row,started) in list(active.items()):
            d=ROOT/'jobs'/('retrac--'+row['task'])
            receipt=d/'health.json'
            status=json.loads(receipt.read_text()) if receipt.exists() else {}
            recent=sorted((d/'api').glob('call-*.json'))[-6:]
            calls=[json.loads(f.read_text()) for f in recent]
            fault=failure(status,calls)
            if fault:add_error(row['task'],fault)
            wall=status.get('solving_started')
            expired=(time.time()-wall>row['wall_seconds']+15 and not status.get('stop_reason')) if wall else time.monotonic()-started>900
            if p.is_alive() and expired:
                add_error(row['task'],'controller_deadline_or_preparation_stall')
        if errors:
            h.update(updated=time.time(),state='stopping_engineering_failure',
                     active=[r['task'] for _,r,_ in active.values()],pending=[r['task'] for r in pending])
            save(ROOT/'health.json',h)
            # Signal every active task before waiting/archiving any of them.
            for p,_,_ in active.values():
                if p.is_alive():
                    try:
                        os.kill(p.pid,signal.SIGSTOP)
                    except ProcessLookupError:pass
            for p,_,_ in active.values():
                if p.is_alive():
                    try:os.kill(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
            for p,_,_ in active.values():terminate_trial(p)
        for slot,(p,row,started) in list(active.items()):
            if p.is_alive():continue
            p.join(.1);d=ROOT/'jobs'/('retrac--'+row['task']);stopped=True
            h.update(updated=time.time(),state='stopping_engineering_failure' if errors else 'collecting',
                     cleanup_task=row['task'],active=[r['task'] for _,r,_ in active.values()],
                     pending=[r['task'] for r in pending])
            save(ROOT/'health.json',h)
            cleanup_error=None
            try:
                if (d/'container.json').exists():
                    c=json.loads((d/'container.json').read_text());cleanup_owned(c['name'],c['job'])
            except Exception as exc:stopped=False;cleanup_error=exc
            r=reconcile(d,row['task'],'retrac--'+row['task'],stopped,cleanup_error,bool(errors))
            if errors:r['batch_halt_reason']=list(errors)
            fault=failure(r)
            if fault:add_error(row['task'],fault)
            save(d/'summary.json',r);done.append(r);del active[slot]
        if not errors and h['canary_state']!='passed' and len(done)>=2:
            if canary_passed(done[:2]):h['canary_state']='passed'
            else:
                h['canary_state']='failed';add_error('canary','live_memory_or_workspace_not_verified')
        limit=4 if h['canary_state']=='passed' else 2
        for slot in range(limit):
            if not errors and pending and slot not in active:
                if h['canary_state']!='passed' and pending[0]['task'] not in canary_names:break
                row=pending.pop(0);p=ctx.Process(target=trial_function,args=(row,[16+slot*2,17+slot*2],key))
                p.start();active[slot]=(p,row,time.monotonic())
        h.update(updated=time.time(),active=[r['task'] for _,r,_ in active.values()],pending=[r['task'] for r in pending],
                 active_pids={r['task']:p.pid for p,r,_ in active.values()},
                 state='admission_paused' if errors else 'running')
        save(ROOT/'health.json',h)
        if errors and not active:break
        time.sleep(2)
    h.update(updated=time.time(),state='needs_attention' if errors or pending else 'generation_complete')
    save(ROOT/'health.json',h)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--credential-file',type=Path,required=True);a=p.parse_args()
    assert a.credential_file.parent==Path('/dev/shm') and a.credential_file.name.startswith('longcli-retrac-')
    assert a.credential_file.stat().st_mode&0o077==0
    key=a.credential_file.read_text().strip();a.credential_file.unlink();worker(key)
