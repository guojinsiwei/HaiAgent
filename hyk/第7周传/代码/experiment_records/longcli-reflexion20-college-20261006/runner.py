"""Four academy Docker tasks; sealed Reflexion engine, immutable artifacts."""
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
sys.path.insert(0,str(ROOT/'reflexion/src'))
from reflexion.audit import JsonlLogger,redact
from reflexion.engine import ReflexionConfig
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
        if event=='terminal_input':self.tools+=1
        if event=='reflection':self.states+=1
        fault=event_failure(event,payload)
        if fault:self.summary['engineering_fault']=fault
        self.summary.update(updated=time.time(),model_calls=self.models,root_tool_dispatches=self.tools,
                            committed_states=self.states,trial=payload.get('trial',self.summary.get('trial')))
        save(self.health,self.summary)

def run_trial(row,cpus,key=None,mock=False,pressure=False,suffix=''):
    os.setsid()
    def stop(_s,_f):raise RuntimeError('Controller deadline reached')
    signal.signal(signal.SIGTERM,stop)
    job=('keyless' if mock else 'reflexion')+'--'+row['task']+suffix
    d=ROOT/('acceptance-jobs' if mock else 'jobs')/job;d.mkdir(parents=True,exist_ok=False)
    h={'job':job,'task':row['task'],'pid':os.getpid(),'state':'preparing','started':time.time(),'paid':not mock,
       'fresh_container':True,'fresh_home':True,'api_key_visible_in_task':False}
    save(d/'health.json',h);terminal=None
    try:
        os.sched_setaffinity(0,cpus)
        resource.setrlimit(resource.RLIMIT_AS,(3*2**30,3*2**30))
        logger=ProgressLogger(d/'trace',d/'health.json',h,secrets=(key,))
        client=MatchedClient(key,d/'api',mock,pressure,'EARLY_FACT_'+secrets.token_hex(12))
        config=ReflexionConfig(max_trials=3,memory_size=3,max_steps_per_trial=40,max_tool_calls=600,max_model_calls=800,
            max_total_seconds=360 if mock else row['wall_seconds'],max_context_chars=48000,
            context_reserve_chars=12000,max_observation_chars=24000,max_reflection_chars=4000,
            max_command_duration=300,max_parse_attempts=2,repeat_action_limit=4)
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
        instruction+='Budgets: 800 model requests including evaluation/reflection/format repair, 600 terminal calls, 4096 output tokens per request, 48000 UTF-8 input bytes.'
        active_terminal=terminal
        if mock and pressure:
            # Native tmux displays only a screenful; thousands of real lines alone
            # do not test the byte boundary. Add visibly SYNTHETIC transport load
            # after the first real isolation observation; never used in paid runs.
            class PressureTerminal:
                def __init__(self,base):self.base=base;self.dispatches=0
                def observe(self):return self.base.observe()
                def execute(self,keys,duration):
                    self.dispatches+=1
                    observed=self.base.execute(keys,duration)
                    if self.dispatches==1:return observed
                    return ('[SYNTHETIC TRANSPORT PRESSURE, NOT TASK EVIDENCE]\n'
                            + ('中文"\\\n'*18000) + '\n[REAL TERMINAL OBSERVATION FOLLOWS]\n'+observed)
            active_terminal=PressureTerminal(terminal)
        result=MatchedRunner(client,config,logger).run(instruction,active_terminal)
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
                 trials=len(result.trials),trial_details=[asdict(r) for r in result.trials],task_processes_stopped=True)
        save(d/'result.json',redact(asdict(result),secrets=(key,)))
        if mock:
            assert result.stop_reason=='evaluator_passed' and not result.error and len(result.trials)==3
            assert len([r for r in result.trials if r.reflection])==2
            assert len(result.memory)==2 and result.official_success is None
            assert (terminal.app/'continuity-proof.txt').read_text().strip()==client.fact
            events=[json.loads(line) for line in (d/'trace/events.jsonl').read_text().splitlines()]
            assert any('ISOLATION_OK' in e.get('observation','') and client.fact in e.get('observation','') for e in events if e['event']=='terminal_output')
            from context_limit import input_bytes
            calls=[json.loads(p.read_text()) for p in (d/'api').glob('mock-request-*.json')]
            assert all(input_bytes({'messages':r['messages']})<=48000 for r in calls)
            if pressure:
                assert any(r.stop_reason=='trial_context_limit' for r in result.trials), 'Byte-pressure did not exercise native context trial boundary'
                assert max(input_bytes({'messages':r['messages']}) for r in calls)>32000
            h.update(state='keyless_pass',maximum_input_bytes=max(input_bytes({'messages':r['messages']}) for r in calls),
                     persistent_terminal_verified=True,reflection_memory_verified=True,
                     native_trials=3,reflections=2,internal_evaluation_is_not_official_score=True)
            if pressure:h['pressure_fixture']='Real pinned tmux plus explicitly labelled synthetic UTF8/JSON transport load; never paid task evidence'
        else:
            contexts=[json.loads(p.read_text()) for p in (d/'api').glob('context-*.json')]
            h.update(state='awaiting_grade',maximum_input_bytes=max((c['after_bytes'] for c in contexts),default=0),
                     artifact=export_tree(terminal.app,d/'final-source.tar.gz',source_only=True))
    except Exception as exc:
        details=redact(str(exc),secrets=(key,))[:700]
        if h.get('error'):h['secondary_controller_error']=details
        else:h['error']=details
        h.update(state='engineering_failure',error_type=type(exc).__name__,updated=time.time())
        # First failure is visible before any potentially blocked cleanup.
        save(d/'health.json',h)
    finally:
        try:
            if terminal:terminal.close()
            elif (d/'container.json').exists():
                receipt=json.loads((d/'container.json').read_text());cleanup_owned(receipt['name'],job,d/'rescued-app')
            h['task_processes_stopped']=True
        except Exception as exc:
            h.update(cleanup_error=type(exc).__name__,task_processes_stopped=bool(getattr(exc,'cleanup_receipt',{}).get('stopped')))
            if getattr(exc,'cleanup_receipt',None):h['cleanup_receipt']=exc.cleanup_receipt
        h.update(ended=time.time(),seconds=time.time()-h['started']);save(d/'summary.json',h);save(d/'health.json',h)
    return h

def terminate_trial(p):
    if not p.is_alive():return
    try:
        # Infrastructure faults are not a graceful solver deadline. Freeze and
        # kill this exact owned child first; parent then rescues its container.
        os.kill(p.pid,signal.SIGSTOP)
        os.kill(p.pid,signal.SIGKILL)
    except ProcessLookupError:return
    p.join(1)
    assert not p.is_alive(),'Child stop could not be confirmed'


def worker(key,trial_function=None,test_tasks=None):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    tasks=list(test_tasks if test_tasks is not None else protocol['tasks'])
    canary_names=protocol['engineering_guard']['canary_tasks']
    canaries=[r for name in canary_names for r in tasks if r['task']==name]
    assert len(canaries)==2
    pending=canaries+[r for r in tasks if r['task'] not in canary_names]
    active={};done=[];errors=[];ctx=multiprocessing.get_context('fork')
    trial_function=trial_function or run_trial
    h={'state':'running','pid':os.getpid(),'completed':done,'errors':errors,
       'canary_state':'pending','engineering_fail_fast':True}
    def add_error(task,reason):
        if not any(e['task']==task and e['reason']==reason for e in errors):
            errors.append({'task':task,'reason':reason,'new_admission_stopped':True})
    while pending or active:
        # Inspect BEFORE new admission. Fatal health/events are live, not just final state.
        for slot,(p,row,started) in list(active.items()):
            d=ROOT/'jobs'/('reflexion--'+row['task'])
            receipt=d/'health.json'
            status=json.loads(receipt.read_text()) if receipt.exists() else {}
            calls=[json.loads(f.read_text()) for f in (d/'api').glob('call-*.json')]
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
            p.join(.1);d=ROOT/'jobs'/('reflexion--'+row['task']);stopped=True
            h.update(updated=time.time(),state='stopping_engineering_failure' if errors else 'collecting',
                     cleanup_task=row['task'],active=[r['task'] for _,r,_ in active.values()],
                     pending=[r['task'] for r in pending])
            save(ROOT/'health.json',h)
            cleanup_error=None
            try:
                if (d/'container.json').exists():
                    c=json.loads((d/'container.json').read_text());cleanup_owned(c['name'],c['job'],d/'rescued-app')
            except Exception as exc:stopped=False;cleanup_error=exc
            r=reconcile(d,row['task'],'reflexion--'+row['task'],stopped,cleanup_error,bool(errors))
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
                row=pending.pop(0);p=ctx.Process(target=trial_function,args=(row,[24+slot*2,25+slot*2],key))
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
    assert a.credential_file.parent==Path('/dev/shm') and a.credential_file.name.startswith('longcli-reflexion-')
    assert a.credential_file.stat().st_mode&0o077==0
    key=a.credential_file.read_text().strip();a.credential_file.unlink();worker(key)
