"""Never send hidden tests or reference solutions to either solver host."""
import json
from pathlib import Path
import shutil
import tarfile
from common import ROOT,sha,save
from college_prepare import TASKS

public=ROOT/'public'
public.mkdir(exist_ok=True)
for task in TASKS:
    source=ROOT/'upstream/tasks_long_cli'/task
    target=public/task
    target.mkdir(exist_ok=True)
    for line in (source/'Dockerfile').read_text().splitlines():
        if not line.startswith('COPY '): continue
        name=line.split()[1].removeprefix('./')
        assert name not in ('tests','run-tests.sh') and '/' not in name
        original=source/name
        if not (target/name).exists():
            if original.is_dir(): shutil.copytree(original,target/name,symlinks=True)
            else: shutil.copy2(original,target/name)
solver_names=('common.py','environment.py','runner.py','worker.py','launch.py','net_transport.py',
              'chroot_entry.py','audit.py','cube_prepare.py','seal.py','refresh_fixtures.py','test_adapter.py')
files=[ROOT/name for name in solver_names]
files += [ROOT/name for name in ('protocol.json','preflight-0.json','preflight-1.json',
          'grading-acceptance.json','roundtrip-acceptance.json','ready.json') if (ROOT/name).exists()]
files += [p for directory in ('sources','public') for p in (ROOT/directory).rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts]
with tarfile.open(ROOT/'solver-inputs.tar.gz','w:gz') as archive:
    for p in files: archive.add(p,arcname=p.relative_to(ROOT).as_posix(),recursive=False)
save(ROOT/'solver-input-manifest.json',dict(files={p.relative_to(ROOT).as_posix():sha(p) for p in files},
    hidden_grader_files_transferred=False,model_calls=0))
print(json.dumps(dict(files=len(files),archive_bytes=(ROOT/'solver-inputs.tar.gz').stat().st_size)))
