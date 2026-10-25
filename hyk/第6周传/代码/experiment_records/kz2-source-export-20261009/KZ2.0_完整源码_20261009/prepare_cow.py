"""One fresh cow run, isolated from the two currently running retries."""
import json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'kz2-retry2-memory-soft-20261009'
ORIGINAL=ROOT.parent/'kz2-low4-20261009'

def main():
    assert ROOT.name=='kz2-cow-timeout-retry-20261009'
    assert not (ROOT/'launch.claim').exists() and not list((ROOT/'jobs').glob('*')), 'Never overwrite a launched attempt'
    for name in ['sources','compatibility','tests']:
        if not (ROOT/name).exists():
            shutil.copytree(BASE/name,ROOT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for p in BASE.glob('*.py'):
        if not (ROOT/p.name).exists():shutil.copyfile(p,ROOT/p.name)
    shutil.copyfile(BASE/'historic-config-lock.json',ROOT/'historic-config-lock.json')
    for name in ['upstream','input-manifest.json']:
        if not (ROOT/name).exists():
            (ROOT/name).symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
    for name in ['jobs','incoming','grades','acceptance-jobs','host-tmp','empty-tests','evidence/test-temp']:
        (ROOT/name).mkdir(parents=True,exist_ok=True)
    source='sources/bestfgs-project/src/bestfgs/lean_runtime.py'
    shutil.copyfile(ROOT/'lean_runtime.py.patch-source',ROOT/source)
    p=json.loads((BASE/'protocol.json').read_text())
    original=json.loads((ORIGINAL/'protocol.json').read_text())
    cow=next(row for row in original['tasks'] if row['task']=='61810_cow')
    p.update(experiment=ROOT.name,name='KZ2.0',revision='cow-timeout-retry1',tasks=[cow],
        total_trials=1,concurrency=1,concurrency_per_arm=1,command_seconds=600,
        task_selection='authorized fresh cow retry after model-60s timeout loop')
    from common import save,sha
    p['safety']['command_timeout_policy']='harness_owned_600s_capped_by_task_deadline'
    save(ROOT/'protocol.json',p)
    hashes={n:sha(ROOT/n) for n in json.loads((ROOT/'historic-config-lock.json').read_text())['source_hashes']}
    differences=[n for n,v in hashes.items() if sha(BASE/n)!=v]
    assert set(differences)=={source,'runner.py','docker_environment.py'},differences
    runtime_changes=[n for n in ['runner.py','docker_environment.py'] if sha(ROOT/n)!=sha(BASE/n)]
    assert runtime_changes==['runner.py','docker_environment.py']
    save(ROOT/'source-provenance.json',dict(name='KZ2.0',revision=p['revision'],base=str(BASE),
        changes_from_previous_attempt=differences,runtime_changes=runtime_changes,source_hashes=hashes,
        old_command_seconds=300,new_command_seconds=600,model_timeout_60_no_longer_shortens_window=True,
        unchanged_task_wall_seconds=7200,unchanged_api_requests=800,unchanged_tools=600,
        unchanged_cost_cap_cny=50,prior_results_preserved=True,fresh_container_and_memory=True))
    print(json.dumps(dict(prepared=True,task='61810_cow',command_seconds=600,paid_model_calls=0)))

if __name__=='__main__':main()
