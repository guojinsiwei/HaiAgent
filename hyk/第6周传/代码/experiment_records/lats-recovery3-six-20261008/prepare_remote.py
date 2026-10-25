"""Six isolated new attempts, fourteen immutable grades preserved by reference."""
import json
from pathlib import Path
import shutil
import time
import hashlib
import sys

OVERLAY=Path(__file__).resolve().parent
ROOT=OVERLAY.parent
OLD=Path('/var/tmp/lizh639-longcli-lats-taco-recovery2-20261007/lats')
TASKS={'cmu15_445_p0','cmu15_445_p1','ap1400_2_hw35','61810_fs','61810_lock','61810_traps'}
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2))
def alive(pid):
    p=Path('/proc')/str(pid)/'stat'
    return bool(pid and p.exists() and p.read_text().rsplit(')',1)[1].split()[0]!='Z')

def main():
    if '--refresh-overlay' in sys.argv:
        assert not (ROOT/'launch.claim').exists(),'Never change a launched campaign'
        old=ROOT/'deployment-overlay.json'
        shutil.copyfile(old,ROOT/('deployment-overlay-before-'+str(time.time_ns())+'.json'))
        hashes={}
        for f in OVERLAY.glob('*.py'):
            if f.name=='prepare_remote.py':continue
            shutil.copyfile(f,ROOT/f.name);hashes[f.name]=sha(f)
        save(old,{'sha256':hashes,'time':time.time(),'model_calls':0})
        print('{"overlay_refreshed":true,"paid_model_calls":0}');return
    assert not (ROOT/'resume-plan.json').exists(),'Already prepared; never overwrite a run'
    assert not alive(read(OLD/'health.json').get('pid'))
    old_plan=read(OLD/'resume-plan.json');preserved={r['task']:r for r in old_plan['preserved']}
    for f in (OLD/'grades').glob('lats--*/result.json'):
        r=read(f)
        if r.get('grading_state')=='complete' and r.get('grading_container_destroyed'):
            preserved[r['task']]={'task':r['task'],'report':str(f),'report_sha256':sha(f)}
    remaining=[r for r in old_plan['run_tasks'] if r['task'] not in preserved]
    assert {r['task'] for r in remaining}==TASKS and len(preserved)==14
    for row in remaining:
        summary=read(OLD/'jobs'/('lats--'+row['task'])/'summary.json')
        assert summary['state']=='engineering_failure' and not alive(summary.get('pid'))
    for f in OLD.glob('*.py'):shutil.copyfile(f,ROOT/f.name)
    overlay_hashes={}
    for f in OVERLAY.glob('*.py'):
        if f.name=='prepare_remote.py':continue
        shutil.copyfile(f,ROOT/f.name);overlay_hashes[f.name]=sha(f)
    for name in ('upstream','input-manifest.json','sources','compatibility','taco_native'):
        f=OLD/name
        if f.exists():(ROOT/name).symlink_to(f.resolve(),target_is_directory=f.is_dir())
    for name in ('jobs','grades','incoming','host-tmp','empty-tests','acceptance-jobs'):(ROOT/name).mkdir()
    fixtures=[]
    for task in ('cmu15_445_p0','61810_traps'):
        for f in sorted((OLD/'jobs'/('lats--'+task)/'model').glob('response-*.json'))[-2:]:
            fixtures.append({'task':task,'source':str(f),'source_sha256':sha(f),
                'content':read(f)['choices'][0]['message']['content']})
    save(ROOT/'failure-fixtures.json',fixtures)
    protocol=read(OLD/'protocol.json')
    protocol.update(experiment=ROOT.name,tasks=remaining,run_tasks=remaining,total_trials=6,concurrency=6)
    protocol['recovery3']={'preserved_grades':14,'fresh_attempts':6,'search_unchanged':True,
        'budget_unchanged':True,'timeout':'all LATS executor calls clamped to 1..300 seconds',
        'json_normalization':'complete object followed by exactly one extra close brace only',
        'repair_code_source':'local overlay, never previous stale server repair copy'}
    save(ROOT/'protocol.json',protocol)
    save(ROOT/'resume-plan.json',dict(method='lats',root=str(ROOT),source=str(OLD),
        concurrency=6,preserved=list(preserved.values()),run_tasks=remaining,time=time.time()))
    save(ROOT/'deployment-overlay.json',{'sha256':overlay_hashes,'time':time.time(),'model_calls':0})
    print(json.dumps({'prepared':True,'preserved':14,'rerun':6,'concurrency':6,'paid_model_calls':0}))

if __name__=='__main__':main()
