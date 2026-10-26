import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
names=['queue_policy.py','campaign.py','agents.py','host_agent.py','entry_harbor.py','container-run.mjs','deadline.mjs',
       'tasks.json','history.json','history-reference.json','test_scheduler.py','README.txt','offline.json']
assert json.loads((ROOT/'offline.json').read_text())['passed']
ready=dict(passed=True,files={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
           native_runtime='frozen repair1',dsh_runtime='frozen unlimited-repair',paid_calls_at_pack=0)
(ROOT/'ready.json').write_text(json.dumps(ready,indent=2))
with tarfile.open(ROOT/'deployment.tar.gz','w:gz') as tar:
    for n in names+['ready.json']:tar.add(ROOT/n,arcname=n)
print(hashlib.sha256((ROOT/'deployment.tar.gz').read_bytes()).hexdigest())
