"""Repackage ONLY unstarted public solver inputs after deployment-only corrections."""
import json
import tarfile
from common import ROOT,sha,save

if (ROOT/'ready.json').exists() or (ROOT/'claims').exists():raise RuntimeError('Never modify an admitted campaign')
seal=json.loads((ROOT/'arm-source-manifest.json').read_text())
for arm in ('v6','v8'):
    actual={p.relative_to(ROOT/'arms'/arm).as_posix():sha(p) for p in (ROOT/'arms'/arm).rglob('*.py')
            if '__pycache__' not in p.parts}
    if actual!=seal[arm]:raise RuntimeError('Frozen algorithm changed')
names=('common.py','environment.py','runner.py','worker.py','launch.py','net_transport.py','chroot_entry.py',
       'audit.py','cube_prepare.py','fixture_runner.py','shared_wire.py','admission.py','test_shared_wire.py',
       'historical-wire-failures.json','protocol.json','arm-source-manifest.json','prepare_cube.py','validate.py')
files=[ROOT/n for n in names]+[p for d in ('arms','public') for p in (ROOT/d).rglob('*')
    if p.is_file() and '__pycache__' not in p.parts]
with tarfile.open(ROOT/'solver-inputs-v2.tar.gz','x:gz',dereference=False) as archive:
    for path in files:archive.add(path,arcname=path.relative_to(ROOT).as_posix(),recursive=False)
save(ROOT/'solver-input-manifest-v2.json',dict(files={p.relative_to(ROOT).as_posix():sha(p) for p in files},
    archive_sha256=sha(ROOT/'solver-inputs-v2.tar.gz'),hidden_grader_files_transferred=False,model_calls=0))
print(json.dumps(dict(packaged=True,model_calls=0)))
