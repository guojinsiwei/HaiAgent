"""Copy the original A implementation, not the v8 candidate. No model requests."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from control import HERE, METHODS, MODEL, PARALLEL_SLOTS, PYTHON, environment, plan, verify_image, execute, source_hashes, config
from prepare import COMMIT, write

BASE = Path('/var/tmp/lizh639-lhtb-mechanism-large-20261001')


def tree_hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()
            and '__pycache__' not in p.parts and '.git' not in p.parts and p.suffix != '.pyc'}


def main():
    if (HERE/'manifest.json').exists() or (HERE/'ready.json').exists():
        raise RuntimeError('Refuse reprepare/reseal; inspect the existing campaign')
    reference = json.loads((HERE/'raw-reference-manifest.json').read_text())
    prior = json.loads((BASE/'manifest.json').read_text())
    seal = json.loads((BASE/'ready.json').read_text())
    if reference['tasks'] != prior['tasks'] or reference['benchmark_commit'] != COMMIT:
        raise RuntimeError('Original RAW twelve-task manifest differs')
    original = tree_hashes(BASE/'arms/common')
    for name, digest in original.items():
        sealed = seal['source_hashes'].get('arms/common/'+name)
        if sealed != digest:
            raise RuntimeError('Original frozen A source changed: '+name)
    # The old scope and reporting infrastructure are not copied. Solver, adapter,
    # tool execution and prompt source are copied byte-for-byte, including limits.
    for folder in ('arms','upstream','fixture'):
        shutil.copytree(BASE/folder, HERE/folder, symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
    copied = tree_hashes(HERE/'arms/common')
    if copied != original:
        raise RuntimeError('Frozen A copy differs')
    if subprocess.check_output(['git','-C',str(HERE/'upstream'),'rev-parse','HEAD'],text=True).strip() != COMMIT:
        raise RuntimeError('Benchmark commit changed')
    write(HERE/'manifest.json',dict(reference,methods=METHODS,total_trials=12,
        selection_rule='EXACT original RAW twelve tasks, one fresh frozen A run each',
        source_release='common-v7-with-v6.1-fixes/A',prior_results_carried=0,
        model=MODEL,parallel_slots=PARALLEL_SLOTS,status='authorized_pending_credential'))
    write(HERE/'prior-results.json',[])
    write(HERE/'run-scope.json',dict(stage='screen',parallel_slots=PARALLEL_SLOTS,disable_disk_guard=True))
    write(HERE/'frozen-source-verification.json',dict(base=str(BASE),sha256=original,
        copied_source_identical=True,original_seal_verified=True))
    for name in ('images.json','verified-digests.json'):
        shutil.copy2(BASE/name,HERE/name)
    for row in reference['tasks']:
        verify_image(row['task'])
        if tree_hashes(BASE/'upstream/tasks'/row['task']) != tree_hashes(HERE/'upstream/tasks'/row['task']):
            raise RuntimeError('Task input copy changed')
    plan()
    for row in reference['tasks']:
        kwargs=config(row,'A1')['agents'][0]['kwargs']
        expected=dict(memory_enabled=False,auto_memory=False,memory_decision=False,
                      stagnation_control=False,route_search=False,semantic_monitor=True,
                      memory_reliability=True,monitor_reliability=True,outcome_reliability=True)
        if any(kwargs.get(k) != v for k,v in expected.items()):
            raise RuntimeError('A switches differ from original')
    subprocess.run([PYTHON,'-B','-m','unittest','discover','-s','arms/common/bestfgs-project/tests',
                    '-p','test_lean*.py'],cwd=HERE,env=environment(),check=True,timeout=240)
    fixture=execute(reference['tasks'][0],'A1',True)
    hashes=source_hashes()
    write(HERE/'ready.json',dict(ready=True,source_hashes=hashes,fixture_audits={'A1':fixture},
        protocol_sha256=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        total_trials=12,model_calls=0,disk_reserve_gib=1,parallel_slots=PARALLEL_SLOTS,
        original_A_identical=True,no_previous_results_or_memories_carried=True,
        supervision_version='supervision-v4-engineering',raw_task_manifest_identical=True))
    print(json.dumps(dict(ready=True,tasks=12,parallel_slots=PARALLEL_SLOTS,
                         original_A_identical=True,fixture_pass=True,model_calls=0)))


if __name__=='__main__':main()
