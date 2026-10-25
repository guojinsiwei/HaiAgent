"""Merge exploration-only changes onto the repaired deployed release."""
import json,hashlib,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'tb2-kz-dsh-transport1-20261017'
with tarfile.open(BASE/'runtime-final.tar.gz') as tar:
    members=[m for m in tar.getmembers() if m.name.startswith(('kz/src/','kz/tests/'))]
    tar.extractall(ROOT/'runtime',members=members,filter='data')
conflicts=[]
for p in (ROOT/'merge-base').glob('*.mjs'):
    current=ROOT/'runtime/kz/src'/p.name
    new=ROOT/'latest-dsh/src'/p.name
    for path in (current,p,new):path.write_text(path.read_text())
    result=subprocess.run(['git','merge-file','-p',str(current),str(p),str(new)],capture_output=True)
    (ROOT/'runtime/kz/src'/p.name).write_bytes(result.stdout)
    if result.returncode:conflicts.append(p.name)
for name in ('exploration-trigger.mjs','exploration-learning.mjs'):
    shutil.copy2(ROOT/'latest-dsh/src'/name,ROOT/'runtime/kz/src'/name)
for name in ('exploration-trigger.test.mjs','exploration-learning.test.mjs'):
    shutil.copy2(ROOT/'latest-dsh/tests'/name,ROOT/'runtime/kz/tests'/name)
for p in (ROOT/'native').glob('test_exploration*.py'):
    s=p.read_text()
    import re
    s=re.sub(r"Path\(__file__\).resolve\(\).parents\[3\]/'experiment_records/[^']*/test-tmp'", "Path(__file__).resolve().parent/'test-tmp'",s)
    p.write_text(s)
print(json.dumps(dict(merge_conflicts=conflicts)))
if conflicts:raise SystemExit(1)
