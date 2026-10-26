"""Adopt live no-tools tasks and dispatch ONLY not-started tasks with frozen code."""
import json,multiprocessing,os,signal,sys,time,subprocess
from pathlib import Path
ROOT=Path('/mnt/sdb/home/lizh639/longcli-dh-tools-ablation40-repair1-20261008')
sys.path.insert(0,str(ROOT))
from common import save,validate
from runner import trial,preserve_task
from admission_guard import AdmissionGuard
METHOD='dh_1234_no_tools'
def alive(pid):
    if not isinstance(pid,int) or pid<2:return False
    p=Path('/proc',str(pid))
    try:
        assert p.stat().st_uid==os.getuid()
        cmd=p.joinpath('cmdline').read_bytes()
        assert str(ROOT).encode() in cmd or b'/mnt/sdb/home/lizh639/dh-tools-output-repair2-ops/resume_no_tools_supervisor.py' in cmd
        return p.joinpath('stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
    except FileNotFoundError:return False
def main(key):
    protocol=validate();assert (ROOT/'tools-retired.json').exists()
    os.close(os.open(ROOT/'no-tools-resume-v2.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    active={};done=[];pending=[];errors=[];admission=AdmissionGuard();children={};fatal=None
    for row in protocol['tasks']:
        row=dict(row,method=METHOD);job=METHOD+'--'+row['task'];d=ROOT/'jobs'/job
        if (d/'summary.json').exists():done.append(job)
        elif (d/'health.json').exists():
            h=json.loads((d/'health.json').read_text());assert alive(h['pid']),job+' has no live worker or summary'
            active[job]=(h['pid'],h['started'])
        else:pending.append(row)
    grader=json.loads((ROOT/'grading-launch.json').read_text())['pid']
    assert alive(grader),'Existing grader must remain alive'
    ctx=multiprocessing.get_context('fork')
    try:
        while active or pending:
            if not alive(grader):raise RuntimeError('grader_exited')
            for job,(pid,began) in list(active.items()):
                d=ROOT/'jobs'/job;h=json.loads((d/'health.json').read_text())
                if (d/'summary.json').exists() and not alive(pid):
                    s=json.loads((d/'summary.json').read_text())
                    if job in children:children.pop(job).join(1)
                    fault=admission.observe(METHOD,s)
                    if fault:raise RuntimeError(fault)
                    if s.get('task_local_error'):errors.append({'job':job,'reason':s['task_local_error']})
                    done.append(job);active.pop(job);continue
                if not alive(pid):raise RuntimeError('missing_summary:'+job)
                if time.time()-h.get('updated',began)>600 or time.time()-began>protocol['wall_seconds']+120:
                    raise RuntimeError('watchdog:'+job)
                if h.get('engineering_fault') or h.get('cleanup_error'):raise RuntimeError('shared_fault:'+job)
            while pending and len(active)<6:
                row=pending.pop(0);job=METHOD+'--'+row['task']
                p=ctx.Process(target=trial,args=(row,key));p.start();children[job]=p;active[job]=(p.pid,time.time())
            save(ROOT/'health.json',{'state':'running','pid':os.getpid(),'updated':time.time(),
                'active':list(active),'pending':[METHOD+'--'+r['task'] for r in pending],'completed':done,
                'errors':errors,'concurrency':6,'retired_methods':['dh_1234_tools'],
                'controller_state':'no_tools_only','source_unchanged':True})
            time.sleep(3)
    except Exception as e:
        fatal=str(e)
        for job,(pid,_) in active.items():
            if alive(pid):os.kill(pid,signal.SIGKILL)
            d=ROOT/'jobs'/job
            if not (d/'summary.json').exists():
                h=json.loads((d/'health.json').read_text())
                try:preserve_task(d,h)
                except Exception as e:errors.append({'job':job,'reason':type(e).__name__})
                h.update(stop_reason='supervisor_fault',task_local_error=fatal,updated=time.time())
                save(d/'summary.json',h)
    save(ROOT/'health.json',{'state':'needs_attention' if fatal or errors else 'generation_complete',
        'pid':os.getpid(),'updated':time.time(),'active':[],'pending':[METHOD+'--'+r['task'] for r in pending],
        'completed':done,'errors':errors,'fatal':fatal,'retired_methods':['dh_1234_tools']})
if __name__=='__main__':main(sys.stdin.readline().strip())
