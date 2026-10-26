"""Fresh recovery roots; completed reports immutable, no credentials or model calls."""
import hashlib
import json
from pathlib import Path
import shutil
import time

ROOT=Path(__file__).resolve().parent
BASE=Path('/mnt/sdb/home/lizh639')
SOURCES={'lats':BASE/'longcli-resume-five-20261007/lats-resume-20261007',
         'taco':BASE/'longcli-taco-clean20-20261007'}
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def alive(pid):
    p=Path('/proc')/str(pid)/'stat'
    return pid and p.exists() and p.read_text().rsplit(')',1)[1].split()[0]!='Z'

def main():
    plans=[]
    for method,old in SOURCES.items():
        h=read(old/'health.json')
        assert not alive(h.get('pid',0)), 'Old scheduler is still alive'
        for f in (old/'jobs').glob('*/health.json'):
            assert not alive(read(f).get('pid',0)), 'Old solver is still alive'
        preserved={}
        for r in read(old/'resume-plan.json').get('preserved',[]):
            assert sha(Path(r['report']))==r['report_sha256']
            preserved[r['task']]=r
        for f in (old/'grades').glob(method+'--*/result.json'):
            r=read(f)
            if r.get('grading_state')=='complete':
                task=r.get('task') or f.parent.name.split('--',1)[1]
                preserved[task]={'task':task,'report':str(f),'report_sha256':sha(f)}
        protocol=read(old/'protocol.json')
        remaining=[r for r in protocol['tasks'] if r['task'] not in preserved]
        assert len(remaining)+len(preserved)==20
        assert len(preserved)==({'lats':4,'taco':15}[method])
        for r in remaining:
            s=old/'jobs'/(method+'--'+r['task'])/'summary.json'
            if s.exists():
                v=read(s)
                assert not (v.get('state')=='awaiting_grade' and not v.get('engineering_fault')),'Grade existing artifact first'
        dest=ROOT/method;dest.mkdir()
        for f in old.glob('*.py'):shutil.copyfile(f,dest/f.name)
        for name in ('upstream','input-manifest.json','sources','compatibility','taco_native'):
            f=old/name
            if f.exists():(dest/name).symlink_to(f.resolve(),target_is_directory=f.is_dir())
        for name in ('jobs','grades','incoming','host-tmp','empty-tests','acceptance-jobs'):(dest/name).mkdir()
        for name in ('repair_runtime.py','resume_worker.py','resume_grader.py','test_resume.py','accept_resume.py'):
            shutil.copyfile(BASE/'longcli-resume-five-20261007'/name,dest/name)
        # JSON mode only at structured actor/value boundaries. No parser salvage,
        # extra model attempts, command rewriting or search changes.
        p=dest/'client.py';code=p.read_text()
        needle="        payload=json.dumps(body,ensure_ascii=False).encode('utf-8')"
        assert code.count(needle)==1
        code=code.replace(needle,"        if purpose.startswith(('actor', 'lats_value')):\n            body['response_format']={'type':'json_object'}\n"+needle)
        p.write_text(code)
        protocol.update(experiment='longcli-recovery2-'+method+'-20261007',methods=[method],
            tasks=remaining,run_tasks=remaining,total_trials=len(remaining),concurrency=6)
        protocol['recovery2']={'completed_preserved':len(preserved),'fresh_attempts':True,
            'transport_json_mode':'actor and lats_value only','budget_unchanged':True,
            'host':'college' if method=='lats' else 'cubestudio',
            'cube_difference':'user/PID/network namespace + private chroot; 3GiB process AS, no per-task 8GiB cgroup'}
        save(dest/'protocol.json',protocol)
        plan={'method':method,'source':str(old),'root':str(dest),'concurrency':6,
              'preserved':list(preserved.values()),'run_tasks':remaining,'time':time.time()}
        save(dest/'resume-plan.json',plan);plans.append(plan)
        shutil.copyfile(ROOT/'test_wire.py',dest/'test_wire.py')
        # Package public runtime only for CubeStudio, never logs or memory pools.
        if method=='taco':
            import tarfile
            with tarfile.open(ROOT/'taco-public.tgz','w:gz',dereference=True) as tar:
                for p in dest.glob('*.py'):tar.add(p,arcname=p.name)
                for name in ('protocol.json','resume-plan.json','taco_native'):
                    tar.add(dest/name,arcname=name)
                for row in remaining:
                    f=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')/('starter-'+row['task']+'.tar.gz')
                    tar.add(f,arcname='starters/'+f.name)
    save(ROOT/'manifest.json',{'arms':plans,'paid_model_calls':0})
    print(json.dumps({p['method']:{'preserved':len(p['preserved']),'remaining':len(p['run_tasks']),'concurrency_cap':6} for p in plans}))

if __name__=='__main__':main()
