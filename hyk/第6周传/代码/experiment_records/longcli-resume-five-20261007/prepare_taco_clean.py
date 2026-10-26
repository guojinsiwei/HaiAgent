"""Prepare a fresh, task-isolated TACO 20-task arm without touching prior results."""
import json
import hashlib
from pathlib import Path
import shutil
import time

BASE=Path('/mnt/sdb/home/lizh639')
SOURCE=BASE/'longcli-lats-taco-small20-20261007'
DEST=BASE/'longcli-taco-clean20-20261007'
HERE=Path(__file__).resolve().parent

def save(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert SOURCE.is_dir() and not DEST.exists(), 'Source missing or clean arm already exists'
    source_health=json.loads((SOURCE/'health.json').read_text())
    assert not source_health.get('active'), 'Do not prepare from an active source campaign'
    protocol=json.loads((SOURCE/'protocol.json').read_text())
    assert len(protocol['tasks'])==20
    DEST.mkdir()
    for path in SOURCE.glob('*.py'):
        shutil.copyfile(path,DEST/path.name)
    for name in ('upstream','input-manifest.json','sources','compatibility','taco_native'):
        path=SOURCE/name
        if path.exists():(DEST/name).symlink_to(path.resolve(),target_is_directory=path.is_dir())
    for name in ('repair_runtime.py','resume_worker.py','resume_grader.py','test_resume.py',
                 'accept_resume.py','launch_taco_clean.py'):
        shutil.copyfile(HERE/name,DEST/name)
    for name in ('jobs','grades','incoming','host-tmp','empty-tests','acceptance-jobs'):
        (DEST/name).mkdir()
    assert not (DEST/'taco-pool.json').exists(), 'Cross-task rule pool must not be copied'
    protocol.update(experiment=DEST.name,methods=['taco'],total_trials=20,
                    run_tasks=protocol['tasks'],concurrency=1,
                    recovery_transport={'model_feedback':'none','completed_results_preserved':0,
                        'task_rule_cache':'fresh per task','timeout_bound_seconds':300,
                        'task_fault_policy':'record per task and continue',
                        'automatic_task_retry':False,'original_model_and_tool_budgets':True})
    save(DEST/'protocol.json',protocol)
    plan={'method':'taco','root':str(DEST),'source':str(SOURCE),'concurrency':1,
          'preserved':[],'run_tasks':protocol['tasks'],'time':time.time()}
    save(DEST/'resume-plan.json',plan)
    save(DEST/'clean-preparation.json',{'state':'prepared','source':str(SOURCE),
        'source_protocol_sha256':sha(SOURCE/'protocol.json'),'tasks':20,
        'old_results_reused':0,'shared_rule_pool_copied':False,
        'model_calls':0,'time':time.time()})
    print(json.dumps({'state':'prepared','tasks':20,'old_results_reused':0,'model_calls':0}))


if __name__=='__main__':main()
