"""Prepare a new BestFGS twelve-task run from frozen prior inputs; no model calls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
BASE = Path('/var/tmp/lizh639-lhtb-bestfgs-v181-only-r1')
FIX = Path('/var/tmp/lizh639-mechanism-integration-20260929/repairs/memory-reliability-v5')


def selected_manifest(original):
    if len(original['tasks']) != 12:
        raise ValueError('Expected original twelve-task manifest')
    return dict(original, tasks=original['tasks'][:], methods=['bestfgs'],
        total_trials=12, status='authorized_pilot_pending_preflight_and_credential',
        selection_rule='All twelve tasks in the pre-existing seeded order; no outcome filtering.',
        source_release='memory-reliability-v5', prior_results_carried=0)


def main():
    if (HERE / 'health.json').exists() or (HERE / 'ready.json').exists():
        raise RuntimeError('Never prepare over a sealed or started run')
    from prepare import write, reserve
    reserve()
    original = json.loads((BASE / 'manifest.json').read_text())
    manifest = selected_manifest(original)
    write(HERE / 'manifest.json', manifest)
    write(HERE / 'prior-results.json', [])
    # Independent copies: no writes to the original frozen checkout.
    for name in ('upstream', 'fixture'):
        if not (HERE / name).exists():
            shutil.copytree(BASE / name, HERE / name, symlinks=True,
                            ignore=shutil.ignore_patterns('__pycache__'))
    selected = {t['task'] for t in manifest['tasks']}
    images = [r for r in json.loads((BASE / 'images.json').read_text()) if r['task'] in selected]
    if len(images) != 12:
        raise RuntimeError('Missing frozen image records')
    for row in images:
        info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', row['image']]))[0]
        if info['Id'] != row['id'] or not any(d.endswith('@' + row['digest']) for d in info.get('RepoDigests', [])):
            raise RuntimeError('Image identity changed: ' + row['task'])
    write(HERE / 'images.json', images)
    write(HERE / 'verified-digests.json', {r['image']: r['digest'] for r in images})
    # Confirm exact repaired method code, independent of adapter integration.
    verified = {}
    for name in ('bestfgs-project', 'hai-project'):
        expected = {str(p.relative_to(FIX / 'sources')): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (FIX / 'sources' / name / 'src').rglob('*.py')}
        actual = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (HERE / name / 'src').rglob('*.py')}
        if expected != actual:
            raise RuntimeError('Repaired source mismatch: ' + name)
        verified.update(actual)
    for name in ('audit.py', 'container_command.py', 'docker_state.py', 'hai_outcomes.py'):
        if (HERE / name).read_bytes() != (FIX / 'sources' / name).read_bytes():
            raise RuntimeError('Repaired infrastructure mismatch: ' + name)
    for name in ('transport.py', 'outcomes.py', 'supervisor.py', 'test_outcomes.py', 'test_supervisor.py'):
        if (HERE / name).read_bytes() != (FIX / 'integration' / name).read_bytes():
            raise RuntimeError('Repaired integration mismatch: ' + name)
        verified[name] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
    write(HERE / 'release-source-verification.json', verified)
    write(HERE / 'preparation.json', dict(state='images_ready', ready_images=12,
        failed=[], updated=time.time(), model_calls=0))
    from control import plan
    plan()
    print(json.dumps(dict(prepared=True, tasks=[t['task'] for t in manifest['tasks']],
        trials=12, verified_method_files=len(verified), model_calls=0)))


if __name__ == '__main__':
    main()
