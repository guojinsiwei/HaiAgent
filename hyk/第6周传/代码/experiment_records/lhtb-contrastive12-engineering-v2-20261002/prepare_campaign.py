"""Reuse public cached inputs only; never credentials, results, jobs or ledgers."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from control import HERE, METHODS, MODEL, PARALLEL_SLOTS, PYTHON, environment, plan, verify_image, execute, source_hashes
from prepare import COMMIT, write

BASE = Path('/var/tmp/lizh639-lhtb-mechanism-large-20261001')


def main():
    if (HERE/'manifest.json').exists() or (HERE/'ready.json').exists():
        raise RuntimeError('Never reprepare/reseal an existing campaign')
    reference = json.loads((HERE/'raw-reference-manifest.json').read_text())
    source_reference = json.loads((BASE/'manifest.json').read_text())
    if reference['tasks'] != source_reference['tasks'] or reference['benchmark_commit'] != COMMIT:
        raise RuntimeError('Prior RAW task inputs do not match cached benchmark manifest')
    write(HERE/'manifest.json', dict(reference, methods=METHODS, total_trials=24,
        selection_rule='EXACT original RAW twelve-task manifest, same order; one fresh run per exploration arm',
        prior_results_carried=0, status='authorized_pending_credential', source_release='contrastive-engineering-repair-v2',
        model=MODEL, parallel_slots=PARALLEL_SLOTS))
    write(HERE/'prior-results.json', [])
    write(HERE/'run-scope.json', dict(stage='screen', parallel_slots=PARALLEL_SLOTS, disable_disk_guard=True))
    for name in ('upstream','fixture'):
        shutil.copytree(BASE/name, HERE/name, symlinks=True, ignore=shutil.ignore_patterns('__pycache__'))
    if subprocess.check_output(['git','-C',str(HERE/'upstream'),'rev-parse','HEAD'], text=True).strip() != COMMIT:
        raise RuntimeError('Benchmark commit changed')
    common = HERE/'arms/common'
    # Only unchanged shared audit helpers are reused. Never overwrite the fixed
    # command executor / DockerState with the prior campaign's implementations.
    for name in ('audit.py','hai_outcomes.py'):
        shutil.copy2(BASE/'arms/common'/name, common/name)
    # The validated deployment already contains HAI's unchanged executor.
    # Verify it against the cached source, rather than overwrite shipped code.
    def project_hashes(root):
        return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                and p.suffix != '.pyc'}
    if project_hashes(BASE/'arms/common/hai-project') != project_hashes(common/'hai-project'):
        raise RuntimeError('Unchanged HAI dependency differs from cached source')
    candidate = json.loads((HERE/'candidate-source-manifest.json').read_text())['candidate']
    actual = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((common/'bestfgs-project/src/bestfgs').glob('*.py'))}
    if candidate != actual:
        raise RuntimeError('Engineering candidate differs from its 160-test validated seal')
    for name in ('images.json','verified-digests.json'):
        shutil.copy2(BASE/name,HERE/name)
    for row in reference['tasks']:
        verify_image(row['task'])
        original_task = BASE/'upstream/tasks'/row['task']
        copied_task = HERE/'upstream/tasks'/row['task']
        for old in original_task.rglob('*'):
            if old.is_file() and '__pycache__' not in old.parts:
                new = copied_task/old.relative_to(original_task)
                if hashlib.sha256(old.read_bytes()).digest() != hashlib.sha256(new.read_bytes()).digest():
                    raise RuntimeError('Official task copy changed')
    plan()
    subprocess.run([PYTHON,'-B','-m','unittest','discover','-s','tests','-v'], cwd=HERE,
                   env=environment(), check=True, timeout=180)
    fixtures = {method:execute(reference['tasks'][0],method,True) for method in METHODS}
    hashes = source_hashes()
    write(HERE/'ready.json', dict(ready=True, source_hashes=hashes, fixture_audits=fixtures,
        protocol_sha256=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        total_trials=24, model_calls=0, disk_reserve_gib=1, parallel_slots=PARALLEL_SLOTS,
        raw_task_manifest_identical=True, validated_candidate_identical=True,
        no_previous_results_or_memories_carried=True))
    print(json.dumps(dict(ready=True,tasks_per_arm=12,total_trials=24,parallel_slots=PARALLEL_SLOTS,
                          fixture_official_passes=2, model_calls=0)))


if __name__ == '__main__': main()
