"""Audited operational amendment; resume the existing guard without reading secrets."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path('/var/tmp/lizh639-lhtb-mechanism-large-20261001')
STAGED = ROOT/'evidence/runtime-policy-incoming'
CHANGED = ['supervisor.py', 'prepare.py', 'arms/common/docker_state.py',
           'PROTOCOL.md', 'test_runtime_policy.py']
sys.path.insert(0, str(ROOT))
from supervisor import identity, read, write
from control import validate, source_hashes, verify_image

ready = validate()
health = read(ROOT/'health.json')
guard = read(ROOT/'guard-started-v2.json')
scheduler = read(ROOT/'guard-health.json')['scheduler_pid']
scheduler_identity = identity(scheduler)
if health.get('active') or health['state'] != 'waiting_for_disk':
    raise RuntimeError('Require an idle disk-paused scheduler for amendment')
if identity(guard['pid']) != guard['identity'] or scheduler_identity is None:
    raise RuntimeError('Original guard and scheduler must be live')
scope = read(STAGED/'run-scope.json')
if (scope.get('stage') != 'pilot_plus3' or scope.get('task_indices') != [1, 5, 0, 2, 3]
        or scope.get('parallel_slots') != 8 or scope.get('disable_disk_guard') is not True):
    raise RuntimeError('Unexpected authorized scope')
manifest = read(ROOT/'manifest.json')
for index in scope['task_indices']:
    verify_image(manifest['tasks'][index]['task'])
backup = ROOT/'evidence'/('runtime-policy-before-'+str(time.time_ns()))
backup.mkdir()
originals = CHANGED + ['ready.json', 'run-scope.json']
for relative in originals:
    source = ROOT/relative
    if source.exists():
        target = backup/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
original_results = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (ROOT/'ledger').glob('*/result.json')}
restarting = False
try:
    for relative in CHANGED:
        shutil.copy2(STAGED/relative, ROOT/relative)
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest',
                             'test_runtime_policy', 'test_deployment', 'test_harness_patch'],
                            cwd=ROOT, capture_output=True, text=True)
    (backup/'regression.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        print((result.stdout+result.stderr)[-6000:])
        raise RuntimeError('Regression failed')
    print('REGRESSION', (result.stdout+result.stderr)[-1500:])
    hashes = source_hashes()
    delta = {p for p in set(hashes)|set(ready['source_hashes'])
             if hashes.get(p) != ready['source_hashes'].get(p)}
    if delta != set(CHANGED):
        raise RuntimeError('Unexpected source delta: '+repr(delta))
    for relative, digest in original_results.items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Existing result changed')
    amended = dict(ready, source_hashes=hashes,
        protocol_sha256=hashlib.sha256((ROOT/'PROTOCOL.md').read_bytes()).hexdigest())
    amended['runtime_policy_amendment'] = dict(timestamp=time.time(), changed=sorted(delta),
        previous_seal_sha256=hashlib.sha256((backup/'ready.json').read_bytes()).hexdigest(),
        preserved_results=original_results, authorized_total_trials=25, parallel_slots=8,
        disable_disk_guard=True, algorithm_sources_unchanged=True,
        reason='User authorized removing disk reserve gates, continuing four pilot jobs, and three additional paired tasks per group',
        backup=str(backup), model_calls_during_amendment=0)
    write(ROOT/'ready.json', amended)
    write(ROOT/'run-scope.json', scope)
    check = subprocess.run([sys.executable, '-B', 'supervisor.py', 'inspect', str(ROOT), 'college'],
                           cwd=ROOT, capture_output=True, text=True)
    if check.returncode:
        print(check.stdout, check.stderr)
        raise RuntimeError('Amended queue validation failed')
    inspection = json.loads(check.stdout)
    if inspection['active'] or inspection['blockers'] or inspection['completed'] != 6:
        raise RuntimeError('Unexpected ledger state before restart')
    if identity(scheduler) != scheduler_identity or identity(guard['pid']) != guard['identity']:
        raise RuntimeError('Original process identity changed')
    restarting = True
    os.kill(scheduler, signal.SIGTERM)
    print(json.dumps(dict(amended=True, preserved_results=len(original_results), total=25,
                          parallel_slots=8, restarted_scheduler_only=True, backup=str(backup))))
except BaseException:
    if not restarting:
        for relative in originals:
            saved = backup/relative
            if saved.exists(): shutil.copy2(saved, ROOT/relative)
            elif relative == 'test_runtime_policy.py': (ROOT/relative).unlink(missing_ok=True)
    raise
