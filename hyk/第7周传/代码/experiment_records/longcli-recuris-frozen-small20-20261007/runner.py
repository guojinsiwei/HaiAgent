"""Single frozen Recuris arm; no oracle feedback, independent matched campaign."""
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from common import ROOT,save,sha,validate
from client import Client
from sandbox import Sandbox,close_owned
from adapter import run_recuris


def run_trial(row,key):
    job=row['method']+'--'+row['task'];d=ROOT/'jobs'/job
    d.mkdir(parents=True,exist_ok=False)
    began=time.monotonic();deadline=began+row['wall_seconds']
    h={'job':job,'task':row['task'],'method':row['method'],'state':'preparing',
       'pid':os.getpid(),'started':time.time(),'updated':time.time(),
       'model_requests':0,'api_attempts':0,'api_responses':0,'tool_calls':0}
    env=None;client=Client(key,d/'model',deadline)
    def health(**fields):
        h.update(fields,updated=time.time());save(d/'health.json',h)
    client.health=health;health()
    try:
        protocol=json.loads((ROOT/'protocol.json').read_text())
        env=Sandbox(row,d,deadline,health)
        health(state='running')
        assert row['method']=='recuris_frozen'
        result=run_recuris(client,env,row['instruction'])
        save(d/'result.json',result)
        assert client.logical<=800 and client.wire<=1600 and env.tools<=600
        env.close();artifact=env.export()
        h.update(result,state='awaiting_grade',artifact=artifact,task_processes_stopped=True)
    except Exception as exc:
        import traceback
        h.update(state='engineering_failure',engineering_fault=type(exc).__name__,
            error_frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name}
                          for f in traceback.extract_tb(exc.__traceback__)[-8:]])
        # No exception strings: provider-generated text may contain a secret.
    finally:
        try:close_owned(d);h['task_processes_stopped']=True
        except Exception as exc:h.update(state='engineering_failure',cleanup_error=type(exc).__name__)
        h.update(model_requests=client.logical,api_attempts=client.wire,model_usage=client.usage,
                 tool_calls=env.tools if env else 0,updated=time.time(),ended=time.time(),
                 seconds=time.monotonic()-began)
        save(d/'summary.json',h);save(d/'health.json',h)
    if h['state']=='awaiting_grade':
        stage=ROOT/'incoming'/('.'+job+'.stage');stage.mkdir(exist_ok=False)
        shutil.copyfile(d/'final-source.tar.gz',stage/'final-source.tar.gz')
        assert sha(stage/'final-source.tar.gz')==h['artifact']['sha256']
        save(stage/'summary.json',h)
        stage.rename(ROOT/'incoming'/job)
    return h


def stop_active(active,errors):
    # Only forked children and containers labelled to this campaign/job.
    for p,_,_ in active.values():
        if p.is_alive():
            try:os.kill(p.pid,signal.SIGSTOP)
            except ProcessLookupError:pass
    for job,(p,_,_) in active.items():
        if p.is_alive():
            try:os.kill(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        p.join(1)
        try:close_owned(ROOT/'jobs'/job)
        except Exception as exc:errors.append({'job':job,'reason':'cleanup_'+type(exc).__name__})
        save(ROOT/'jobs'/job/'interruption.json',{'state':'stopped_with_batch','time':time.time()})
    active.clear()


def worker(key):
    active={};errors=[]
    try:return work(key,active,errors)
    except BaseException as exc:
        errors.append({'reason':'controller_'+type(exc).__name__})
        stop_active(active,errors)
        save(ROOT/'health.json',{'state':'needs_attention','errors':errors,'active':[], 'updated':time.time()})
        raise


def work(key,active,errors):
    protocol=validate();ctx=multiprocessing.get_context('fork')
    scratch=ROOT/'host-tmp';scratch.mkdir(exist_ok=True);os.environ['TMPDIR']=str(scratch)
    import tempfile
    tempfile.tempdir=str(scratch)
    pending={m:[dict(r,method=m) for r in protocol['tasks']] for m in protocol['methods']}
    done=[];pilot_jobs={m+'--'+t for m in protocol['methods'] for t in protocol['canaries']}
    with (ROOT/'grading-worker.log').open('x') as out,(ROOT/'grading-stderr.log').open('x') as err:
        grader=subprocess.Popen([sys.executable,'-B',str(ROOT/'grading_worker.py')],stdin=subprocess.DEVNULL,
                                stdout=out,stderr=err,start_new_session=True)
    save(ROOT/'grading-launch.json',{'pid':grader.pid,'model_calls':0})
    h={'state':'running','pid':os.getpid(),'started':time.time(),'errors':errors}
    while active or any(pending.values()):
        gh=ROOT/'grading-health.json'
        if gh.exists() and json.loads(gh.read_text()).get('errors'):errors.append({'reason':'grading_failure'})
        if grader.poll() is not None:errors.append({'reason':'grading_worker_exited_early'})
        for job,(p,row,began) in list(active.items()):
            d=ROOT/'jobs'/job;hp=d/'health.json';status=json.loads(hp.read_text()) if hp.exists() else {}
            if status.get('engineering_fault') or status.get('cleanup_error'):
                errors.append({'job':job,'reason':'trial_engineering_failure'})
            if p.is_alive() and (time.time()-status.get('updated',began)>600 or time.time()-began>row['wall_seconds']+120):
                errors.append({'job':job,'reason':'stalled_or_wall_overrun'})
            if not p.is_alive():
                p.join(1);sp=d/'summary.json';summary=json.loads(sp.read_text()) if sp.exists() else {}
                if p.exitcode!=0 or summary.get('state')!='awaiting_grade' or not (ROOT/'incoming'/job).is_dir():
                    errors.append({'job':job,'reason':'invalid_delivery'})
                else:done.append(job)
                del active[job]
        if errors:stop_active(active,errors);break
        pilot_complete=all((ROOT/'grades'/j/'result.json').exists() for j in pilot_jobs)
        for method,queue in pending.items():
            if not queue or len(active)>=protocol['concurrency']:continue
            capacity=protocol['concurrency'] if pilot_complete else 1
            if len(active)>=capacity:continue
            # First two tasks per arm ARE part of the 40, not extra paid tests.
            if queue[0]['task'] not in protocol['canaries'] and not pilot_complete:continue
            row=queue.pop(0);job=method+'--'+row['task']
            p=ctx.Process(target=run_trial,args=(row,key));p.start();active[job]=(p,row,time.time())
        h.update(updated=time.time(),active=list(active),completed=done,
                 pending={m:[r['task'] for r in q] for m,q in pending.items()},pilot_complete=pilot_complete)
        save(ROOT/'health.json',h);time.sleep(3)
    h.update(state='needs_attention' if errors else 'generation_complete',active=[],updated=time.time())
    save(ROOT/'health.json',h)


if __name__=='__main__':
    raise SystemExit('Use launch.py with a fresh credential on encrypted stdin.')
