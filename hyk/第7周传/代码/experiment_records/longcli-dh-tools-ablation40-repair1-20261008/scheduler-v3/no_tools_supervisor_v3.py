"""Resume frozen trials. An observation error never terminates healthy siblings."""
import json,multiprocessing,os,signal,sys,time
from pathlib import Path
ROOT=Path('/mnt/sdb/home/lizh639/longcli-dh-tools-ablation40-repair1-20261008')
METHOD='dh_1234_no_tools'

def process_status(pid,root=ROOT,expected_start=None,proc_root=Path('/proc'),uid=None):
    if type(pid) is not int or pid<2:return {'status':'exited'}
    p=proc_root/str(pid)
    try:
        fields=(p/'stat').read_text().rsplit(')',1)[1].split()
        if fields[0] in ('Z','X'):return {'status':'exited','start':fields[19]}
        start=fields[19]
        if expected_start is not None and str(expected_start)!=start:return {'status':'reused','start':start}
        if p.stat().st_uid!=(os.getuid() if uid is None else uid):return {'status':'foreign','start':start}
        cmd=(p/'cmdline').read_bytes()
        if not cmd:return {'status':'unknown','start':start,'reason':'empty_live_cmdline'}
        if str(root).encode() not in cmd:return {'status':'foreign','start':start}
        final=(p/'stat').read_text().rsplit(')',1)[1].split()
        if final[0] in ('Z','X'):return {'status':'exited','start':start}
        if final[19]!=start:return {'status':'reused','start':final[19]}
        return {'status':'running','start':start}
    except FileNotFoundError:return {'status':'exited'}
    except (OSError,IndexError,ValueError) as error:return {'status':'unknown','reason':type(error).__name__}

def error_record(error,job=None):
    return {'job':job,'error_type':type(error).__name__,'reason':type(error).__name__}

def main(key):
    sys.path.insert(0,str(ROOT))
    from common import save,validate
    from runner import trial,preserve_task
    protocol=validate()
    os.close(os.open(ROOT/'no-tools-resume-v3.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    active={};done=[];pending=[];errors=[];children={};fatal=None;warnings={};streak=(None,0)
    for row in protocol['tasks']:
        row=dict(row,method=METHOD);job=METHOD+'--'+row['task'];d=ROOT/'jobs'/job
        if (d/'summary.json').exists():done.append(job)
        elif (d/'health.json').exists():
            h=json.loads((d/'health.json').read_text());state=process_status(h.get('pid'))
            active[job]={'pid':h.get('pid'),'began':h.get('started',time.time()),'start':state.get('start')}
        else:pending.append(row)
    ctx=multiprocessing.get_context('fork')
    def publish():
        save(ROOT/'health.json',{'state':'needs_attention' if fatal else 'running' if active or pending else 'generation_complete',
            'pid':os.getpid(),'updated':time.time(),'active':list(active),
            'pending':[METHOD+'--'+r['task'] for r in pending],'completed':done,'errors':errors,
            'fatal':fatal,'warnings':warnings,'concurrency':6,'retired_methods':['dh_1234_tools'],
            'controller_state':'v3_no_sibling_kill','source_unchanged':True})
    def fail_one(job,info,reason):
        state=process_status(info['pid'],expected_start=info.get('start'))
        if state['status']=='unknown':warnings[job]=state;return
        if state['status']=='running':
            try:os.kill(info['pid'],signal.SIGKILL)
            except ProcessLookupError:pass
        d=ROOT/'jobs'/job;hp=d/'health.json'
        h=json.loads(hp.read_text()) if hp.exists() else {'job':job}
        h.update(task_local_error=reason,error_type=reason,stop_reason=reason,updated=time.time(),ended=time.time())
        try:preserve_task(d,h)
        except Exception as e:h.update(state='engineering_failure',artifact_error=type(e).__name__)
        save(d/'summary.json',h);save(hp,h)
    publish()
    while active or (pending and not fatal):
        try:
            gp=ROOT/'grading-launch.json'
            grader=process_status(json.loads(gp.read_text()).get('pid')) if gp.exists() else {'status':'exited'}
            gh=ROOT/'grading-health.json';g=json.loads(gh.read_text()) if gh.exists() else {}
            if grader['status'] in ('exited','foreign','reused') or g.get('errors'):fatal=fatal or 'grading_unavailable'
        except Exception as e:fatal=fatal or 'grading_status_'+type(e).__name__;errors.append(error_record(e))
        for job,info in list(active.items()):
            try:
                d=ROOT/'jobs'/job;state=process_status(info['pid'],expected_start=info.get('start'))
                if (d/'summary.json').exists():
                    if state['status']=='running':continue
                    if state['status']=='unknown':warnings[job]=state;continue
                    s=json.loads((d/'summary.json').read_text())
                    if job in children:children.pop(job).join(0)
                    reason=s.get('task_local_error') or s.get('engineering_fault') or s.get('cleanup_error')
                    if reason:
                        errors.append({'job':job,'reason':reason});old,n=streak;streak=(reason,n+1 if old==reason else 1)
                        if streak[1]>=2:fatal=fatal or 'repeated_engineering_failure:'+reason
                    else:streak=(None,0)
                    done.append(job);active.pop(job);warnings.pop(job,None);continue
                if state['status']=='unknown':
                    warnings[job]=state;fatal=fatal or 'process_observation_uncertain';continue
                if state['status'] in ('exited','foreign','reused'):
                    fail_one(job,info,'worker_exit_without_summary');continue
                hp=d/'health.json';h=json.loads(hp.read_text()) if hp.exists() else {}
                if h.get('engineering_fault') or h.get('cleanup_error'):fatal=fatal or 'worker_shared_fault'
                if time.time()-h.get('updated',info['began'])>600 or time.time()-info['began']>protocol['wall_seconds']+120:
                    fail_one(job,info,'watchdog_timeout')
            except Exception as e:
                fatal=fatal or 'supervisor_observation_'+type(e).__name__;errors.append(error_record(e,job))
                # Keep healthy children, registry and artifacts intact; only pause new admissions.
        while pending and len(active)<6 and not fatal:
            row=pending[0];job=METHOD+'--'+row['task']
            try:
                p=ctx.Process(target=trial,args=(row,key));p.start();children[job]=p
                state=process_status(p.pid)
                active[job]={'pid':p.pid,'began':time.time(),'start':state.get('start')};pending.pop(0)
            except Exception as e:fatal='dispatch_'+type(e).__name__;errors.append(error_record(e,job));break
        publish();time.sleep(3)
    publish()

if __name__=='__main__':main(sys.stdin.readline().strip())
