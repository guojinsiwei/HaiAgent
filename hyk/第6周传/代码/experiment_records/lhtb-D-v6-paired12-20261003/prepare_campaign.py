"""Verify and copy frozen D and the already validated v6 engineering repair."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from control import HERE, METHODS, MODEL, PARALLEL_SLOTS, PYTHON, environment, plan, verify_image, execute, source_hashes, config
from prepare import COMMIT, write

BASE=Path('/var/tmp/lizh639-lhtb-mechanism-large-20261001')
V6=Path('/var/tmp/lizh639-monitor-control-v6.1')


def hashes(root,python_only=False):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*.py' if python_only else '*')) if p.is_file()
            and '__pycache__' not in p.parts and '.git' not in p.parts and p.suffix!='.pyc'}


def main():
    if (HERE/'ready.json').exists():
        raise RuntimeError('Refuse reprepare/reseal; inspect first')
    if (HERE/'manifest.json').exists():
        # Resume credential-free deployment validation, not any paid task.
        if (HERE/'ledger').exists() or (HERE/'runs').exists():
            raise RuntimeError('Never change inputs after production admission')
        reference=json.loads((HERE/'raw-reference-manifest.json').read_text())
        frozen=json.loads((HERE/'frozen-source-verification.json').read_text())
        for method in METHODS:
            if hashes(HERE/'arms'/method)!=frozen[method]['sha256']:
                raise RuntimeError('Prepared frozen source changed')
        for row in reference['tasks']:
            verify_image(row['task'])
            if hashes(BASE/'upstream/tasks'/row['task'])!=hashes(HERE/'upstream/tasks'/row['task']):
                raise RuntimeError('Prepared task copy changed')
        plan()
        finish_preflight(reference)
        return
    reference=json.loads((HERE/'raw-reference-manifest.json').read_text())
    original=json.loads((BASE/'manifest.json').read_text())
    seal=json.loads((BASE/'ready.json').read_text())
    if reference['tasks']!=original['tasks'] or reference['benchmark_commit']!=COMMIT:
        raise RuntimeError('Reference twelve-task manifest changed')
    d_hashes=hashes(BASE/'arms/common')
    if any(seal['source_hashes'].get('arms/common/'+p)!=digest for p,digest in d_hashes.items()):
        raise RuntimeError('D original frozen source changed')
    fixed=json.loads((V6/'fixed-source-manifest.json').read_text())
    integration=json.loads((V6/'integration-source-manifest.json').read_text())
    if hashes(V6/'sources',True)!=fixed or hashes(V6/'integration',True)!=integration:
        raise RuntimeError('Validated v6.1 release seal changed')
    for row in json.loads((V6/'baseline-manifest.json').read_text()):
        if hashlib.sha256(Path(row['origin']).read_bytes()).hexdigest()!=row['sha256']:
            raise RuntimeError('Original v6 baseline changed')
    (HERE/'arms').mkdir()
    shutil.copytree(BASE/'arms/common',HERE/'arms/D1',symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(V6/'sources',HERE/'arms/V1',symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(V6/'integration/transport.py',HERE/'arms/V1/transport.py')
    if hashes(HERE/'arms/D1')!=d_hashes or hashes(HERE/'arms/V1',True)!={**fixed,'transport.py':integration['transport.py']}:
        raise RuntimeError('Frozen arm copy differs')
    for name in ('upstream','fixture'):
        shutil.copytree(BASE/name,HERE/name,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
    if subprocess.check_output(['git','-C',str(HERE/'upstream'),'rev-parse','HEAD'],text=True).strip()!=COMMIT:
        raise RuntimeError('Benchmark commit changed')
    write(HERE/'manifest.json',dict(reference,methods=METHODS,total_trials=24,
        selection_rule='EXACT original RAW twelve tasks; D and v6 each one fresh full run',
        source_release={'D1':'common-v7-with-v6.1-fixes/D','V1':'monitor-control-v6.1'},
        prior_results_carried=0,model=MODEL,parallel_slots=PARALLEL_SLOTS,status='authorized_pending_credential',
        arm_order='Alternate D/V within each task; both methods have identical task inputs and budgets'))
    write(HERE/'prior-results.json',[])
    write(HERE/'run-scope.json',dict(stage='screen',parallel_slots=PARALLEL_SLOTS,disable_disk_guard=True))
    write(HERE/'frozen-source-verification.json',dict(D1=dict(base=str(BASE),sha256=d_hashes),
        V1=dict(base=str(V6),sha256=hashes(HERE/'arms/V1')),copied_source_identical=True,
        v6_engineering_repair_explicit=True,no_new_algorithm_changes=True))
    for name in ('images.json','verified-digests.json'):shutil.copy2(BASE/name,HERE/name)
    for row in reference['tasks']:
        verify_image(row['task'])
        if hashes(BASE/'upstream/tasks'/row['task'])!=hashes(HERE/'upstream/tasks'/row['task']):
            raise RuntimeError('Official task copy changed')
    plan()
    finish_preflight(reference)


def finish_preflight(reference):
    regression=[]
    for method in METHODS:
        for label,args in (
            ('lean',['-m','unittest','discover','-s',f'arms/{method}/bestfgs-project/tests','-p','test_lean*.py']),
            ('wire',['-m','unittest','discover','-s',f'arms/{method}/bestfgs-project/tests','-p','test_retrac_adapter.py']),
            ('deployment',['-m','unittest','test_deployment']),
        ):
            log=HERE/f'{method}-{label}-regression.log'
            if log.exists():
                number=1
                while (HERE/f'{method}-{label}-regression-{number}.log').exists():number+=1
                log=HERE/f'{method}-{label}-regression-{number}.log'
            # Test examples are not part of the production import path. The
            # adapter's HTTP mocks import examples.demo_counter from this root.
            test_env=environment(method)
            test_env['PYTHONPATH']=os.pathsep.join([str(HERE/'arms'/method/'bestfgs-project'),test_env['PYTHONPATH']])
            with log.open('x') as stream:
                subprocess.run([PYTHON,'-B',*args],cwd=HERE,env=test_env,
                    stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=240)
            regression.append(method+'/'+label)
    # Explicitly version credential-free synthetic validation attempts. Failed
    # reports remain untouched; this never retries a production benchmark task.
    attempt=1
    while any((HERE/'fixtures'/config(reference['tasks'][0],method,True,attempt)['job_name']).exists()
              or (HERE/(config(reference['tasks'][0],method,True,attempt)['job_name']+'.console.log')).exists()
              for method in METHODS):attempt+=1
    fixtures={method:execute(reference['tasks'][0],method,True,attempt) for method in METHODS}
    sealed=source_hashes()
    write(HERE/'ready.json',dict(ready=True,source_hashes=sealed,fixture_audits=fixtures,
        protocol_sha256=hashlib.sha256(json.dumps(sealed,sort_keys=True).encode()).hexdigest(),
        total_trials=24,model_calls=0,disk_reserve_gib=1,parallel_slots=PARALLEL_SLOTS,
        original_D_identical=True,validated_v6_1_identical=True,no_previous_results_or_memories_carried=True,
        raw_task_manifest_identical=True,regression_groups=regression))
    print(json.dumps(dict(ready=True,tasks_per_arm=12,total_trials=24,parallel_slots=PARALLEL_SLOTS,
        original_D_identical=True,validated_v6_1_identical=True,fixture_passes=2,model_calls=0)))


if __name__=='__main__':main()
