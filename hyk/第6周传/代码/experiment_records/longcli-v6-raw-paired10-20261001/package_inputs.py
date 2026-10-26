"""Create auditable input bundles without exposing grader assets to solvers."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from college_prepare import ROOT, TASKS, sha

commit = subprocess.check_output(['git','-C',str(ROOT/'upstream'),'rev-parse','HEAD'],text=True).strip()
assert commit == '2015f37b5c458f2562354de6b415e9182c91af64'
files = {}
with tarfile.open(ROOT/'college-inputs.tar.gz','w:gz') as archive:
    for base in [ROOT/'upstream/longcli_dockerImage', ROOT/'upstream/terminal_bench',
                 *[ROOT/'upstream/tasks_long_cli'/task for task in TASKS]]:
        for path in sorted(base.rglob('*')):
            if '__pycache__' in path.parts or '.git' in path.parts:
                continue
            if path.is_symlink():
                raise RuntimeError('Unexpected link in trusted grading inputs: '+str(path))
            if path.is_file():
                name = path.relative_to(ROOT).as_posix()
                files[name] = sha(path)
                archive.add(path,arcname=name,recursive=False)
    for path in [ROOT/'college_prepare.py']:
        files[path.name] = sha(path)
        archive.add(path,arcname=path.name)
    manifest = dict(commit=commit, files=files, tasks=TASKS)
    (ROOT/'input-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    archive.add(ROOT/'input-manifest.json',arcname='input-manifest.json')
print(json.dumps(dict(commit=commit, files=len(files), bytes=(ROOT/'college-inputs.tar.gz').stat().st_size)))
