"""Fresh two-task retry; copy no jobs, logs, memory, keys, or scores."""
import json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'kz2-low4-20261009'

def main():
    assert ROOT.name=='kz2-retry2-memory-soft-20261009'
    assert not (ROOT/'sources').exists(), 'Do not overwrite an existing deployment'
    for name in ['sources','compatibility','tests']:
        shutil.copytree(BASE/name,ROOT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for p in BASE.glob('*.py'):
        if not (ROOT/p.name).exists():shutil.copyfile(p,ROOT/p.name)
    shutil.copyfile(BASE/'historic-config-lock.json',ROOT/'historic-config-lock.json')
    for name in ['upstream','input-manifest.json']:
        (ROOT/name).symlink_to(BASE/name,target_is_directory=(BASE/name).is_dir())
    for name in ['jobs','incoming','grades','acceptance-jobs','host-tmp','empty-tests','evidence/test-temp']:
        (ROOT/name).mkdir(parents=True,exist_ok=True)
    source=ROOT/'sources/bestfgs-project/src/bestfgs/memory_injection.py'
    shutil.copyfile(ROOT/'memory_injection.py.patch-source',source)
    p=json.loads((BASE/'protocol.json').read_text())
    rows={r['task']:r for r in p['tasks']}
    p.update(experiment=ROOT.name,name='KZ2.0',revision='memory-prose-soft-retry1',
        tasks=[rows[t] for t in ['61810_mmap','cmu15_445_p2']],total_trials=2,
        concurrency=2,concurrency_per_arm=2,
        task_selection='authorized fresh retry of mmap and cmu_p2; cow/lock untouched')
    from common import save,sha
    p['safety']['memory_review_length_is_advisory']=True
    save(ROOT/'protocol.json',p)
    hashes={n:sha(ROOT/n) for n in json.loads((ROOT/'historic-config-lock.json').read_text())['source_hashes']}
    differences=[n for n,v in hashes.items() if sha(BASE/n)!=v]
    assert differences==['sources/bestfgs-project/src/bestfgs/memory_injection.py'],differences
    save(ROOT/'source-provenance.json',dict(name='KZ2.0',revision=p['revision'],base=str(BASE),
        changes_from_previous_attempt=differences,source_hashes=hashes,
        prior_results_preserved=True,fresh_container_and_memory=True))
    print(json.dumps(dict(prepared=True,tasks=list(rows[t]['task'] for t in ['61810_mmap','cmu15_445_p2']),paid_model_calls=0)))

if __name__=='__main__':main()
