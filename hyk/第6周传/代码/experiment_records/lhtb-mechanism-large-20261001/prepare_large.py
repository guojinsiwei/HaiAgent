"""Credential-free deployment, fixed development/holdout split, no paid launch."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from control import HERE,plan,verify_image,source_hashes,environment,PYTHON
from prepare import COMMIT,write,reserve

BASE=Path('/var/tmp/lizh639-lhtb-bestfgs12-memory-v5-20260930')
SEED='lhtb-file-artifacts-triple25-20260926'
EXCLUDED={'genetic-convergence-testing','generals-bot-arena','vector-db-iterative-build'}

def split(inventory):
    eligible=[t for t in inventory['tasks'] if t['agent'].get('continue_until_timeout') and t['task'] not in EXCLUDED]
    ordered=sorted(eligible,key=lambda t:hashlib.sha256((SEED+'/'+t['task']).encode()).hexdigest())
    if len(ordered)!=28:raise ValueError('Expected exactly 28 eligible tasks')
    for row in ordered:
        for item in row['artifacts']:
            path=item['source'] if isinstance(item,dict) else item
            if path.startswith('/') and not path.startswith('/app/'):raise ValueError('Artifact outside /app')
    return ordered[:12],ordered[12:]

def main():
    if (HERE/'ready.json').exists() or (HERE/'manifest.json').exists():raise RuntimeError('Already prepared; inspect first')
    reserve()
    dev,holdout=split(json.loads((HERE/'inventory.json').read_text()))
    prior=json.loads((BASE/'manifest.json').read_text())
    if [t['task'] for t in dev]!=[t['task'] for t in prior['tasks']]:raise RuntimeError('Development split changed')
    from control import METHODS
    write(HERE/'manifest.json',dict(prior,tasks=dev,methods=METHODS,total_trials=120,
        selection_rule='First 12 in original seeded order; five mechanism groups; two fresh repetitions',
        source_release='common-v7-with-v6.1-fixes',prior_results_carried=0))
    write(HERE/'holdout-plan.json',dict(tasks=holdout,total_trials=144,repetitions=3,groups_count=3,
        baseline='A',finalists='Two groups selected from B/C/D/E using development data only',
        state='pending_development_analysis_and_image_validation'))
    write(HERE/'prior-results.json',[])
    write(HERE/'run-scope.json',dict(stage='pilot',pilot_task_indices=[1,5],pilot_trials=10))
    for folder in ('upstream','fixture'):
        shutil.copytree(BASE/folder,HERE/folder,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
    if subprocess.check_output(['git','-C',str(HERE/'upstream'),'rev-parse','HEAD'],text=True).strip()!=COMMIT:
        raise RuntimeError('Benchmark commit changed')
    image_rows=json.loads((BASE/'images.json').read_text())
    write(HERE/'images.json',image_rows)
    for task in dev:verify_image(task['task'])
    write(HERE/'verified-digests.json',{r['image']:r['digest'] for r in image_rows})
    hashes={p.relative_to(HERE/'arms/common').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((HERE/'arms/common').rglob('*.py'))}
    write(HERE/'release-source-verification.json',dict(common=hashes))
    plan()
    print(json.dumps(dict(development=12,holdout=16,pilot_trials=10,screen_trials=120,
                          planned_total=264,model_calls=0)))

if __name__=='__main__':main()
