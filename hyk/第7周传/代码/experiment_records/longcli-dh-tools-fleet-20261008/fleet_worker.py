"""Task-disjoint fleet sidecar: no algorithm/budget changes, no action retries."""
import argparse,json,multiprocessing,os,subprocess,sys,time
from pathlib import Path
from common import ROOT,save,sha,validate

def alive(pid):
    if not isinstance(pid,int) or pid<2:return False
    try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
    except (OSError,IndexError):return False

def configure(mode):
    import runner
    if mode=='cube':
        from cube_environment import CubeEnvironment,close_cube
        runner.DockerEnvironment=CubeEnvironment;runner.close_owned=close_cube
        def preserve(d,h,mock=False):
            close_cube(d);h['task_processes_stopped']=True
            workspace=d/'rootfs/app'
            if workspace.is_dir():
                h['artifact']=runner.export_tree(workspace,d/'final-source.tar.gz',source_only=True)
                h['state']='keyless_failure' if mock else 'awaiting_grade'
        runner.preserve_task=preserve
    return runner

def check(slot,mode,accept=False):
    if mode=='college':validate()
    else:
        # Grader orchestration stays on the academy node, never in solver roots.
        ready=json.loads((ROOT/'ready.json').read_text());assert ready['ready']
        for name,expected in ready['hashes'].items():
            if name=='college_grader.py':continue
            assert sha(ROOT/name)==expected,'Sealed solver source changed: '+name
    plan=json.loads((ROOT/'fleet-plan.json').read_text())
    rows=plan['assignments'][slot]
    assert rows and len({r['task'] for r in rows})==len(rows)
    if accept:
        runner=configure(mode)
        if mode=='cube':
            result=runner.trial(dict(rows[0],method='dh_tools'),mock=True)
            assert result['state']=='keyless_pass',result
            env_class=runner.DockerEnvironment
            d=ROOT/'acceptance-jobs'/('fleet-restore-'+str(time.time_ns()));d.mkdir()
            try:
                env=env_class(rows[0],d)
                cp=env.checkpoint('canary')
                r=env.execute({'argv':['sh','-c','echo changed > canary'],'timeout_seconds':10},time.monotonic()+15)
                assert r.return_code==0
                env.restore(cp);assert env.scope()==cp['fingerprint']
                # Host files and host network must remain inaccessible.
                test=env.probe('import os,json,socket;print(json.dumps({"uid":os.getuid(),"cpus":len(os.sched_getaffinity(0)),"tests":os.path.exists("/tests"),"host":os.path.exists("/mnt/lizh639")}))')
                x=json.loads(test);assert x=={'uid':0,'cpus':2,'tests':False,'host':False},x
                native=env.execute({'argv':['sh','-c','printf aa >/dev/null; test ! -s /dev/null'],'timeout_seconds':10},time.monotonic()+15)
                assert native.return_code==0 and not native.stderr
            finally:runner.close_owned(d)
        save(ROOT/('fleet-accepted-'+slot+'.json'),{'passed':True,'mode':mode,'paid_model_calls':0,
            'code_hashes':{name:sha(ROOT/name) for name in ('fleet_worker.py','cube_environment.py','chroot_entry.py')},
            'time':time.time()})
    accepted=json.loads((ROOT/('fleet-accepted-'+slot+'.json')).read_text())
    assert accepted['passed']
    assert all(sha(ROOT/n)==v for n,v in accepted['code_hashes'].items())
    return rows

def loop(slot,mode,key):
    runner=configure(mode);rows=check(slot,mode);pending=list(rows);active={};done=[];errors=[]
    ctx=multiprocessing.get_context('fork');own_jobs={'dh_tools--'+r['task'] for r in rows}
    cap=8 if mode=='college' else 2
    while active or pending:
        for job,(process,row) in list(active.items()):
            p=ROOT/'jobs'/job/'health.json';h=json.loads(p.read_text()) if p.exists() else {}
            if process.is_alive() and time.time()-h.get('updated',time.time())>600:
                process.kill();process.join(5)
                runner.preserve_task(ROOT/'jobs'/job,h)
                h.update(task_local_error='watchdog_timeout',ended=time.time(),updated=time.time())
                save(ROOT/'jobs'/job/'summary.json',h)
            if not process.is_alive():
                process.join();sp=ROOT/'jobs'/job/'summary.json';s=json.loads(sp.read_text()) if sp.exists() else {}
                if s.get('state')=='awaiting_grade':done.append(job)
                else:errors.append({'job':job,'reason':s.get('error_type') or s.get('cleanup_error') or 'missing_delivery'})
                if s.get('engineering_fault') or s.get('cleanup_error'):
                    # Stop admission but let other already-running owned tasks settle.
                    pending=[];errors.append({'job':job,'reason':'shared_backend_admission_stopped'})
                active.pop(job)
        outsiders=0
        if mode=='college':
            for d in (ROOT/'jobs').iterdir():
                if d.name in own_jobs:continue
                p=d/'health.json';h=json.loads(p.read_text()) if p.exists() else {}
                if not (d/'summary.json').exists() and alive(h.get('pid')):outsiders+=1
        control=ROOT/'fleet-control.json'
        paused=control.exists() and json.loads(control.read_text()).get('pause_admission')
        while pending and not paused and len(active)+outsiders<cap:
            row=pending.pop(0);job='dh_tools--'+row['task']
            assert not (ROOT/'jobs'/job).exists(),'Duplicate task attempt forbidden'
            process=ctx.Process(target=runner.trial,args=(dict(row,method='dh_tools'),key));process.start()
            active[job]=(process,row)
        state='running' if active or pending else ('needs_attention' if errors else 'generation_complete')
        save(ROOT/('fleet-'+slot+'-health.json'),{'state':state,'pid':os.getpid(),'updated':time.time(),
            'active':list(active),'pending':['dh_tools--'+r['task'] for r in pending],
            'completed':done,'errors':errors,'concurrency_limit':cap,'outside_active':outsiders,
            'worker_node':slot,'mode':mode})
        if active or pending:time.sleep(3)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--slot',required=True)
    ap.add_argument('--mode',choices=['college','cube'],required=True)
    ap.add_argument('--accept',action='store_true');ap.add_argument('--check',action='store_true')
    args=ap.parse_args()
    if args.accept or args.check:
        rows=check(args.slot,args.mode,args.accept)
        print(json.dumps({'ready':True,'tasks':len(rows),'slot':args.slot,'model_calls':0}));return
    rows=check(args.slot,args.mode)
    key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
    claim=ROOT/('fleet-'+args.slot+'-launch.claim')
    os.close(os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    pid=os.fork()
    if pid:
        save(ROOT/('fleet-'+args.slot+'-launch.json'),{'pid':pid,'time':time.time(),'tasks':len(rows)})
        print(json.dumps({'started':True,'slot':args.slot,'pid':pid,'tasks':len(rows)}));return
    os.setsid();sys.stdin=open(os.devnull)
    for stream,fd in (('out',1),('err',2)):
        log=os.open(ROOT/('fleet-'+args.slot+'-'+stream+'.log'),os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600)
        os.dup2(log,fd);os.close(log)
    try:loop(args.slot,args.mode,key)
    except Exception as error:save(ROOT/('fleet-'+args.slot+'-health.json'),{
        'state':'needs_attention','error_type':type(error).__name__,'pid':os.getpid(),'updated':time.time()})
    os._exit(0)

if __name__=='__main__':main()
