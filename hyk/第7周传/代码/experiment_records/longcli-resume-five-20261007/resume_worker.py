"""One independent arm; task failures do not kill unrelated paid tasks."""
import json
import multiprocessing as mp
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from common import ROOT,save,sha


def read(path):return json.loads(path.read_text()) if path.exists() else {}


def trial(row,key,slot):
    from runner import run_trial
    from repair_runtime import install
    install(row['method'])
    if row['method']=='retrac':run_trial(row,[16+slot*2,17+slot*2],key)
    else:run_trial(row,key)


def cleanup(job,method):
    d=ROOT/'jobs'/job
    if method=='retrac':
        from docker_terminal import cleanup_owned
        c=read(d/'container.json')
        if c:cleanup_owned(c['name'],c['job'])
    elif method=='dh':
        from docker_environment import close_owned
        close_owned(d)
    else:
        from sandbox import close_owned
        close_owned(d)


def valid(summary):
    return (summary.get('state')=='awaiting_grade' and summary.get('artifact')
        and summary.get('task_processes_stopped') and not summary.get('engineering_fault')
        and not summary.get('cleanup_error') and not summary.get('error'))


def worker(key):
    plan=read(ROOT/'resume-plan.json');method=plan['method']
    pending=list(plan['run_tasks']);active={};done=[];errors=[]
    ctx=mp.get_context('fork')
    os.environ['TMPDIR']=str(ROOT/'host-tmp')
    import tempfile
    tempfile.tempdir=str(ROOT/'host-tmp')
    h={'state':'running','pid':os.getpid(),'started':time.time(),'method':method,
       'reused_completed':len(plan['preserved']),'errors':errors}
    save(ROOT/'health.json',h)
    with (ROOT/'grading-worker.log').open('x') as out,(ROOT/'grading-stderr.log').open('x') as err:
        grader=subprocess.Popen([sys.executable,'-B',str(ROOT/'resume_grader.py')],
            stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
    save(ROOT/'grading-launch.json',{'pid':grader.pid,'model_calls':0})
    try:
        while pending or active:
            for slot,(p,row,began) in list(active.items()):
                job=method+'--'+row['task'];d=ROOT/'jobs'/job
                status=read(d/'health.json')
                expired=(time.time()-began>row['wall_seconds']+180 or
                         time.time()-status.get('updated',began)>660)
                if p.is_alive() and not expired:continue
                if p.is_alive():p.kill()
                p.join(2)
                cleanup(job,method)
                summary=read(d/'summary.json')
                if p.exitcode==0 and valid(summary):done.append(job)
                else:
                    errors.append({'job':job,'reason':'deadline_or_stall' if expired else
                        summary.get('engineering_fault') or summary.get('stop_reason') or 'missing_delivery',
                        'other_tasks_continue':True})
                del active[slot]
            for slot in range(plan['concurrency']):
                if pending and slot not in active:
                    row=dict(pending.pop(0),method=method)
                    p=ctx.Process(target=trial,args=(row,key,slot));p.start()
                    active[slot]=(p,row,time.time())
            h.update(updated=time.time(),active=[method+'--'+r['task'] for _,r,_ in active.values()],
                     active_pids={r['task']:p.pid for p,r,_ in active.values()},
                     pending=[r['task'] for r in pending],completed=done,errors=errors)
            save(ROOT/'health.json',h);time.sleep(3)
        h.update(state='needs_attention' if errors else 'generation_complete',active=[],updated=time.time())
        save(ROOT/'health.json',h)
    except BaseException as exc:
        for p,row,_ in active.values():
            if p.is_alive():p.kill()
            p.join(2)
            cleanup(method+'--'+row['task'],method)
        h.update(state='needs_attention',active=[],updated=time.time(),
                 controller_error=type(exc).__name__)
        save(ROOT/'health.json',h)
        raise


if __name__=='__main__':
    key=sys.stdin.readline().strip()
    assert key
    worker(key)
