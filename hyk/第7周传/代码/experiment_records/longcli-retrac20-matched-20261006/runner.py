"""Frozen RE-TRAC core, same tasks/rootfs/budgets, two processes per worker."""
import argparse
from dataclasses import asdict
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import resource
import re
import signal
import secrets
import shutil
import sys
import time

from common import ROOT,save,export_tree
from device_setup import prepare_devices

BASE=Path('/mnt/lizh639/longcli-dh-raw-full20-20261004')
DSH=Path('/mnt/lizh639/longcli-dsh20-matched-summary-budget-20261005')
sys.path.insert(0,str(ROOT/'retrac/src'))
from retrac.audit import JsonlLogger,redact
from retrac.engine import RetracConfig
from matched_adapter import MatchedClient,MatchedRunner
from pty_terminal import PersistentTerminal


class ProgressLogger(JsonlLogger):
    def __init__(self,directory,health_path,summary,**kwargs):
        super().__init__(directory,**kwargs)
        self.health_path,self.summary=health_path,summary
        self.models=self.tools=self.compressions=0
    def write(self,event,**payload):
        super().write(event,**payload)
        if event=='model_request':self.models+=1
        if event=='command':self.tools+=1
        if event=='compressed_state':self.compressions+=1
        self.summary.update(updated=time.time(),model_calls=self.models,root_tool_dispatches=self.tools,
            committed_states=self.compressions,round=payload.get('round',self.summary.get('round')))
        save(self.health_path,self.summary)


def fresh_root(row,job):
    import subprocess
    root=ROOT/'roots'/hashlib.sha256(job.encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=False)
    subprocess.run(['cp','-a','--reflink=auto',str(BASE/'templates'/row['family'])+'/.',str(root)],check=True,timeout=600)
    app=root/'app';app.mkdir(exist_ok=True)
    for source in (BASE/'public'/row['task']).iterdir():
        if source.is_dir():shutil.copytree(source,app/source.name,symlinks=True)
        else:shutil.copy2(source,app/source.name)
    for tree in (app,root/'tmp'):
        for parent,dirs,files in os.walk(tree,followlinks=False):
            os.chown(parent,65534,65534,follow_symlinks=False)
            for name in dirs+files:os.chown(Path(parent)/name,65534,65534,follow_symlinks=False)
    prepare_devices(root)
    assert not (root/'tests/run-tests.sh').exists()
    return root


def run_trial(row,cpus,key=None,mock=False,pressure=False,suffix=''):
    os.setsid()
    def stop(_sig,_frame):raise RuntimeError('Harness process deadline reached')
    signal.signal(signal.SIGTERM,stop)
    job=('keyless' if mock else 'retrac')+'--'+row['task']+suffix
    directory=ROOT/('acceptance-jobs' if mock else 'jobs')/job
    directory.mkdir(parents=True,exist_ok=False)
    summary={'job':job,'task':row['task'],'state':'preparing','started':time.time(),
        'fresh_rootfs':True,'fresh_home':True,'paid':not mock,'api_key_visible_in_task':False}
    save(directory/'health.json',summary)
    terminal=None
    try:
        os.sched_setaffinity(0,cpus)
        root=fresh_root(row,job)
        resource.setrlimit(resource.RLIMIT_AS,(3*2**30,3*2**30))
        logger=ProgressLogger(directory/'trace',directory/'health.json',summary,secrets=(key,))
        fact='EARLY_FACT_'+secrets.token_hex(12)
        client=MatchedClient(key,directory/'api',mock,pressure,fact)
        config=RetracConfig(rounds=8,max_steps_per_round=50,max_tool_calls=600,max_model_calls=800,
            max_total_seconds=360 if mock else row['wall_seconds'],max_context_chars=48000,
            compression_reserve_chars=12000,max_observation_chars=24000,max_state_chars=8000,
            max_command_duration=300,max_parse_attempts=2,summary_variant='full')
        terminal=PersistentTerminal(root,cpus,logger)
        if mock:
            terminal.observe()
            terminal.execute('sleep 10\n',0.1)
            terminal.execute('C-c',0.2)
            assert 'CONTROL_OK' in terminal.execute("printf 'CONTROL_OK\\n'\n",0.2), 'Ctrl-C did not interrupt foreground job'
        summary.update(state='running',updated=time.time(),solving_started=time.time(),configuration=asdict(config),cpu_affinity=cpus)
        save(directory/'health.json',summary)
        task='Run the keyless continuity test.' if mock else row['instruction']
        task+='\nWork in /app; only /app files are delivered. Hidden tests and external task networking are unavailable. '
        task+='Budgets: 800 model requests including compression/format repair, 600 terminal calls, '
        task+='4096 output tokens per request, 48000 UTF-8 input bytes. Preserve the existing persistent terminal protocol.'
        result=MatchedRunner(client,config,logger).run(task,terminal)
        terminal.close();terminal=None
        summary.update(stop_reason=result.stop_reason,model_calls=result.model_calls,
            logical_model_requests=result.model_calls,api_attempts=client.wire_attempts,
            root_tool_dispatches=result.tool_calls,rounds=len(result.rounds),round_details=[asdict(r) for r in result.rounds],
            input_tokens=result.input_tokens,output_tokens=result.output_tokens,error=redact(result.error,secrets=(key,)),
            task_processes_stopped=True)
        # Public audit snapshots permit checking real progress during solving.
        shutil.copyfile(directory/'trace/events.jsonl',directory/'events.jsonl')
        save(directory/'result.json',redact(asdict(result),secrets=(key,)))
        contexts=[json.loads(p.read_text()) for p in (directory/'api').glob('context-*.json')]
        summary['maximum_input_bytes']=max((r['after_bytes'] for r in contexts),default=0)
        if mock:
            assert result.stop_reason=='rounds_completed' and result.error is None and len(result.rounds)==8
            assert len([r for r in result.rounds if r.state])==7
            assert (root/'app/continuity-proof.txt').read_text().strip()==fact
            raw_events=[json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]
            assert any(re.search(r'(?m)^ISOLATION_OK\r?$',e.get('output','')) for e in raw_events if e['event']=='tool_result')
            requests=[json.loads(p.read_text()) for p in (directory/'api').glob('mock-request-*.json')]
            assert max(input_bytes({'messages':r['messages']}) for r in requests)<=48000
            summary.update(state='keyless_pass',persistent_terminal_verified=True,
                recursive_memory_verified=True,maximum_input_bytes=max(input_bytes({'messages':r['messages']}) for r in requests))
        else:
            summary.update(state='awaiting_grade',artifact=export_tree(root/'app',directory/'final-source.tar.gz',source_only=True))
    except Exception as exc:
        summary.update(state='engineering_failure',error_type=type(exc).__name__,error=redact(str(exc),secrets=(key,))[:700])
    finally:
        if terminal:terminal.close()
        summary.update(ended=time.time(),seconds=time.time()-summary['started'],task_processes_stopped=True)
        save(directory/'summary.json',summary);save(directory/'health.json',summary)
    return summary


def input_bytes(body):
    from context_limit import input_bytes as size
    return size(body)


def worker(worker_id,key):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    resources=json.loads((BASE/f'resources-{worker_id}.json').read_text())
    pending=[r for r in protocol['tasks'] if r['index']%2==worker_id]
    active={};completed=[];errors=[]
    health={'worker':worker_id,'pid':os.getpid(),'updated':time.time(),'state':'waiting_for_shared_workers',
        'active':[],'pending':[r['task'] for r in pending],'completed':[],'errors':errors}
    # Do not overlap benchmark generation: keep the same cores and eliminate
    # CPU/RAM competition with the still-running DSH campaign.
    while True:
        clear=True
        for w in (0,1):
            p=DSH/f'health-{w}.json'
            if not p.exists():clear=False;break
            h=json.loads(p.read_text())
            if h.get('active') or h.get('state') not in ('generation_complete','needs_attention','paused'):
                clear=False;break
        health.update(updated=time.time());save(ROOT/f'health-{worker_id}.json',health)
        if clear:break
        time.sleep(15)
    context=multiprocessing.get_context('fork')
    while pending or active:
        for slot in range(2):
            if not errors and pending and slot not in active:
                row=pending.pop(0)
                process=context.Process(target=run_trial,args=(row,resources['cpu_slots'][slot],key))
                process.start()
                active[slot]=(process,row,time.monotonic())
        for slot,(process,row,start) in list(active.items()):
            job='retrac--'+row['task'];d=ROOT/'jobs'/job
            # Preparation has a separate bounded allowance; the engine wall
            # budget starts after preparation, as in the matched DSH run.
            p=d/'health.json';h=json.loads(p.read_text()) if p.exists() else {}
            wall_start=h.get('solving_started')
            expired=time.time()-wall_start>row['wall_seconds']+15 if wall_start else time.monotonic()-start>1800
            if process.is_alive() and expired:
                # Controller must not leave a task namespace executing forever.
                # The engine ordinarily terminates first; this is fail-closed.
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                process.join(15)
                if process.is_alive():
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.join(15)
            if not process.is_alive():
                process.join()
                receipt=d/'summary.json'
                result=json.loads(receipt.read_text()) if receipt.exists() else {'job':job,'task':row['task'],
                    'state':'engineering_failure','error_type':'MissingProcessReceipt'}
                completed.append(result);del active[slot]
                if result['state']=='engineering_failure':errors.append({'task':row['task'],'reason':result.get('error_type')})
                for f in (d/'api').glob('call-*.json'):
                    c=json.loads(f.read_text())
                    if c.get('status') in (400,401,403,429):errors.append({'task':row['task'],'reason':'provider_http'})
        health.update(updated=time.time(),state='admission_paused' if errors else 'running',
            active=[r['task'] for _,r,_ in active.values()],pending=[r['task'] for r in pending],completed=completed)
        save(ROOT/f'health-{worker_id}.json',health)
        if errors and not active:break
        time.sleep(5)
    health.update(updated=time.time(),state='needs_attention' if pending else 'generation_complete')
    save(ROOT/f'health-{worker_id}.json',health)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=int,required=True)
    parser.add_argument('--credential-file',type=Path,required=True);args=parser.parse_args()
    path=args.credential_file
    assert path.parent==Path('/dev/shm') and path.name.startswith('longcli-retrac-') and path.stat().st_mode&0o077==0
    key=path.read_text().strip();path.unlink();worker(args.worker,key)
