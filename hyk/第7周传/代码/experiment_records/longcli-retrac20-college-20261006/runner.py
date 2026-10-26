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

class ProgressLogger(JsonlLogger):
    def __init__(self,directory,health,summary,**kwargs):
        super().__init__(directory,**kwargs);self.health=health;self.summary=summary
        self.models=self.tools=self.states=0
    def write(self,event,**payload):
        super().write(event,**payload)
        if event=='model_request':self.models+=1
        if event=='command':self.tools+=1
        if event=='compressed_state':self.states+=1
        self.summary.update(updated=time.time(),model_calls=self.models,root_tool_dispatches=self.tools,
                            committed_states=self.states,round=payload.get('round',self.summary.get('round')))
        save(self.health,self.summary)

def run_trial(row,cpus,key=None,mock=False,pressure=False,suffix=''):
    os.setsid()
    def stop(_s,_f):raise RuntimeError('Controller deadline reached')
    signal.signal(signal.SIGTERM,stop)
    job=('keyless' if mock else 'retrac')+'--'+row['task']+suffix
    d=ROOT/('acceptance-jobs' if mock else 'jobs')/job;d.mkdir(parents=True,exist_ok=False)
    h={'job':job,'task':row['task'],'state':'preparing','started':time.time(),'paid':not mock,
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
        h.update(state='engineering_failure',error_type=type(exc).__name__,error=redact(str(exc),secrets=(key,))[:700])
    finally:
        try:
            if terminal:terminal.close()
            elif (d/'container.json').exists():
                receipt=json.loads((d/'container.json').read_text());cleanup_owned(receipt['name'],job,d/'rescued-app')
            h['task_processes_stopped']=True
        except Exception as exc:h.update(cleanup_error=type(exc).__name__,task_processes_stopped=False)
        h.update(ended=time.time(),seconds=time.time()-h['started']);save(d/'summary.json',h);save(d/'health.json',h)
    return h

def worker(key):
    protocol=json.loads((ROOT/'protocol.json').read_text());pending=list(protocol['tasks'])
    active={};done=[];errors=[];ctx=multiprocessing.get_context('fork')
    h={'state':'running','pid':os.getpid(),'completed':done,'errors':errors}
    while pending or active:
        for slot in range(4):
            if not errors and pending and slot not in active:
                row=pending.pop(0);p=ctx.Process(target=run_trial,args=(row,[16+slot*2,17+slot*2],key))
                p.start();active[slot]=(p,row,time.monotonic())
        for slot,(p,row,started) in list(active.items()):
            d=ROOT/'jobs'/('retrac--'+row['task']);receipt=d/'health.json'
            status=json.loads(receipt.read_text()) if receipt.exists() else {}
            wall=status.get('solving_started')
            expired=time.time()-wall>row['wall_seconds']+15 if wall else time.monotonic()-started>900
            if p.is_alive() and expired:
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                p.join(15)
                if p.is_alive():
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    p.join(15)
            if p.is_alive():continue
            p.join()
            # Cleanup also runs on unexpected child death (including OOM).
            stopped=True
            try:
                if (d/'container.json').exists():
                    c=json.loads((d/'container.json').read_text());cleanup_owned(c['name'],c['job'],d/'rescued-app')
            except Exception:stopped=False
            s=d/'summary.json'
            r=json.loads(s.read_text()) if s.exists() else {'task':row['task'],'job':'retrac--'+row['task'],
                'state':'engineering_failure','error_type':'MissingProcessReceipt'}
            r['task_processes_stopped']=stopped
            if not stopped:errors.append({'task':row['task'],'reason':'cleanup_failed'})
            if r['state']=='engineering_failure':errors.append({'task':row['task'],'reason':r.get('error_type')})
            api_errors=[json.loads(f.read_text()) for f in (d/'api').glob('call-*.json')]
            if any(c.get('status') in (400,401,403,429) for c in api_errors):
                errors.append({'task':row['task'],'reason':'provider_http'})
            if r.get('stop_reason')=='model_error':errors.append({'task':row['task'],'reason':'model_error_inspect_before_admission'})
            done.append(r);del active[slot]
        h.update(updated=time.time(),active=[r['task'] for _,r,_ in active.values()],pending=[r['task'] for r in pending],
                 state='admission_paused' if errors else 'running')
        save(ROOT/'health.json',h)
        if errors and not active:break
        time.sleep(5)
    h.update(updated=time.time(),state='needs_attention' if pending else 'generation_complete');save(ROOT/'health.json',h)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--credential-file',type=Path,required=True);a=p.parse_args()
    assert a.credential_file.parent==Path('/dev/shm') and a.credential_file.name.startswith('longcli-retrac-')
    assert a.credential_file.stat().st_mode&0o077==0
    key=a.credential_file.read_text().strip();a.credential_file.unlink();worker(key)
