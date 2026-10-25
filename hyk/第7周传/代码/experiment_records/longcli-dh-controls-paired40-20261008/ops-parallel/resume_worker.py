"""Replace ONLY the controller, adopting all running trials without restarting them."""
import json,multiprocessing,os,signal,sys,time
from pathlib import Path
from identity import process_status,AdoptedProcess
from scheduler_ops import dispatch
OPS=Path(__file__).resolve().parent


def inventory(root,protocol,schedule):
    active={};done=[];pending=[]
    for row in schedule(protocol):
        job=row['method']+'--'+row['task'];d=root/'jobs'/job
        hp=d/'health.json';sp=d/'summary.json'
        if not d.exists():pending.append(row);continue
        if not hp.exists():raise RuntimeError('task_starting_without_health_retry_handoff')
        h=json.loads(hp.read_text());state=process_status(h.get('pid'),root)
        if state['status']=='unknown':raise RuntimeError('task_identity_uncertain')
        if state['status']=='running':
            active[job]=(AdoptedProcess(h['pid'],state['start'],root),row,h['started'])
        elif sp.exists():done.append(job)
        else:raise RuntimeError('unfinished_dead_task_requires_explicit_repair')
    return active,done,pending


def main(key,root):
    assert key and not any(c.isspace() for c in key)
    sys.path.insert(0,str(root))
    from common import save,validate
    from runner import trial,schedule,preserve_task
    from admission_guard import AdmissionGuard
    protocol=validate()
    assert protocol['concurrency']==12 and protocol['concurrency_per_arm']==6
    old=json.loads((root/'health.json').read_text());pid=old['pid']
    state=process_status(pid,root)
    assert state['status']=='running' and state.get('process_state') not in ('T','t')
    assert b'run_worker.py' in (Path('/proc')/str(pid)/'cmdline').read_bytes()
    assert not old.get('fatal') and not old.get('errors')
    grader=json.loads((root/'grading-launch.json').read_text())['pid']
    gs=process_status(grader,root);assert gs['status']=='running'
    claim=OPS/'handoff.claim'
    os.close(os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    stopped=False;retired=False
    try:
        os.kill(pid,signal.SIGSTOP);stopped=True
        until=time.monotonic()+10
        while time.monotonic()<until:
            observed=process_status(pid,root,state['start'])
            if observed.get('process_state') in ('T','t'):break
            time.sleep(.1)
        assert observed.get('process_state') in ('T','t'),'controller_not_frozen'
        assert observed['start']==state['start']
        active,done,pending=inventory(root,protocol,schedule)
        save(OPS/'before-handoff.json',json.loads((root/'health.json').read_text()))
        save(OPS/'handoff.json',dict(time=time.time(),original_controller=pid,original_start=state['start'],
            adopted={j:dict(pid=p.pid,start=p.start) for j,(p,_,_) in active.items()},completed=done,
            pending=[x['method']+'--'+x['task'] for x in pending],solver_source_unchanged=True,
            budgets_unchanged=True,task_restarts=0,concurrency=12,concurrency_per_arm=6))
        # Signal exactly the checked controller PID, NEVER a process group or worker.
        assert process_status(pid,root,state['start']).get('process_state') in ('T','t')
        os.kill(pid,signal.SIGKILL);retired=True
        until=time.monotonic()+5
        while process_status(pid,root,state['start'])['status']=='running' and time.monotonic()<until:time.sleep(.1)
        assert process_status(pid,root,state['start'])['status']!='running'
    finally:
        if stopped and not retired and process_status(pid,root,state['start'])['status']=='running':
            os.kill(pid,signal.SIGCONT)
    scratch=root/'host-tmp';os.environ['TMPDIR']=str(scratch)
    import tempfile
    tempfile.tempdir=str(scratch)
    ctx=multiprocessing.get_context('fork')
    def spawn(row):
        process=ctx.Process(target=trial,args=(row,key));process.start();return process
    def status(job,final):
        p=root/'jobs'/job/('summary.json' if final else 'health.json')
        return json.loads(p.read_text()) if p.exists() else {}
    def preserve(job,health):
        try:preserve_task(root/'jobs'/job,health)
        except Exception as error:health.update(state='engineering_failure',cleanup_error=type(error).__name__)
        health.update(ended=time.time(),updated=time.time())
        save(root/'jobs'/job/'summary.json',health);save(root/'jobs'/job/'health.json',health)
        return health
    def watchdog(job,process,health):
        if process.is_alive():process.kill()
        process.join(2)
        if isinstance(process,AdoptedProcess):
            until=time.monotonic()+5
            while process.is_alive() and time.monotonic()<until:time.sleep(.1)
        if process.is_alive():raise RuntimeError('owned_worker_not_stopped')
        health.update(state='engineering_failure',task_local_error='watchdog_timeout')
        preserve(job,health)
    def recover_exit(job,process):
        health=status(job,False)
        health.update(state='engineering_failure',task_local_error='worker_exit_without_summary')
        return preserve(job,health)
    def shared_fault():
        s=process_status(grader,root,gs['start'])
        if s['status']!='running':return 'grading_worker_unavailable'
        p=root/'grading-health.json'
        if p.exists() and len(json.loads(p.read_text()).get('errors',{}))>=2:return 'repeated_grading_failure'
    result=dispatch(protocol,pending,spawn=spawn,status=status,admission=AdmissionGuard(),
        heartbeat=lambda h:save(root/'health.json',dict(h,pid=os.getpid())),watchdog=watchdog,
        recover_exit=recover_exit,shared_fault=shared_fault,initial_active=active,initial_done=done,
        require_pilot=False)
    if result['fatal']:raise RuntimeError('admission_paused_healthy_workers_preserved')


if __name__=='__main__':main(sys.stdin.readline().strip(),Path(sys.argv[1]).resolve())
