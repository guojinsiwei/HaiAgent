"""Stage a new immutable four-task run from the verified KZ repaired candidate."""
import json,shutil
from pathlib import Path
from common import ROOT,save,sha

HISTORIC=Path('/mnt/sdb/home/lizh639/longcli-dh-1342-complete20-20261009')
CANDIDATE=Path('/mnt/sdb/home/lizh639/KZ-no-recovery-stop-20261009')
TASKS=['61810_cow','61810_lock','61810_mmap','cmu15_445_p2']

def main():
    assert ROOT.name=='kz2-low4-20261009'
    proof=json.loads((CANDIDATE/'evidence/no-recovery-stop-acceptance.json').read_text())
    assert proof['passed']==47 and proof['proof']['verified_core_files']==136
    for name in ['sources','compatibility']:
        shutil.copytree(CANDIDATE/name,ROOT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(CANDIDATE/'tests',ROOT/'tests',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for file in CANDIDATE.glob('*.py'):
        target=ROOT/file.name
        if not target.exists():shutil.copyfile(file,target)
    shutil.copyfile(HISTORIC/'KZ-config-lock.json',ROOT/'historic-config-lock.json')
    for name in ['upstream','input-manifest.json']:
        (ROOT/name).symlink_to(HISTORIC/name,target_is_directory=(HISTORIC/name).is_dir())
    for name in ['jobs','incoming','grades','acceptance-jobs','host-tmp','empty-tests','evidence/test-temp']:
        (ROOT/name).mkdir(parents=True,exist_ok=True)
    original=json.loads((HISTORIC/'protocol.json').read_text())
    rows={r['task']:r for r in original['tasks']}
    protocol=dict(original,experiment=ROOT.name,name='KZ2.0',tasks=[rows[t] for t in TASKS],
        total_trials=4,concurrency=4,concurrency_per_arm=4,preserved_original_tasks=[],
        task_selection='explicitly authorized rerun of cow, lock, mmap, cmu_p2; preserve historic20',
        safety={'per_task_cny':50,'accounting':'pre-request conservative reservation',
                'all_roles_and_retries':True,'recovery_rejection_hard_stop':False})
    save(ROOT/'protocol.json',protocol)
    from verify_contract import verify
    changed=verify(ROOT)
    save(ROOT/'source-provenance.json',dict(name='KZ2.0',base=str(HISTORIC),candidate=str(CANDIDATE),
        changed_core_files=changed['changed_core_files'],unchanged_core_files=134,
        solver_model_and_budgets_unchanged=True,previous_results_untouched=True,
        source_hashes={name:sha(ROOT/name) for name in json.loads((ROOT/'historic-config-lock.json').read_text())['source_hashes']}))
    print(json.dumps(dict(name='KZ2.0',prepared=True,tasks=TASKS,concurrency=4,paid_model_calls=0)))

if __name__=='__main__':main()
