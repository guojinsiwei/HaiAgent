from pathlib import Path
import hashlib,json,time
R=Path('/mnt/sdb/home/lizh639/appworld-three-arm30-20261018');B=R/'repair-v1';S=B/'stage'
def read(p):return json.loads(p.read_text())
original=read(R/'ready.json');deployed=read(B/'deployed.json');entry=read(S/'entry-acceptance.json')
assert entry['passed'] and len(entry['checks'])==4 and entry['paid_calls']==0
assert read(B/'offline-tests.json')['passed']
allowed=set(deployed['changes'])|{'budget-profile.json'}
hashes={}
for name,expected in original['hashes'].items():
    actual=hashlib.sha256((R/name).read_bytes()).hexdigest()
    if actual!=expected:assert name in allowed,('unplanned change',name)
    hashes[name]=actual
for name in ['runner_repair.py','repair_classification.py','repair_plan.py','spending.py','status.py','budget-profile.json','repair-v1/resume-plan.json']:
    hashes[name]=hashlib.sha256((R/name).read_bytes()).hexdigest()
for arm in ['hld','kzdsh-new','recuris','dsh']:
    for rel in ['boot-guard.mjs','spending-client.mjs']+(['src/budget.mjs','.runtime/kz.patch.yml'] if arm in ['hld','kzdsh-new'] else []):
        name='runtime/'+arm+'/'+rel
        assert (R/name).read_bytes()==(S/name).read_bytes(),('staged entry differs',name)
        hashes[name]=hashlib.sha256((R/name).read_bytes()).hexdigest()
ready={'passed':True,'time':time.time(),'hashes':hashes,'entry_checks':4,'offline_tests':13,'paid_acceptance_calls':0,'budget_limits_cny':{'attempt':8,'campaign':720}}
(B/'ready.json').write_text(json.dumps(ready,indent=2))
print(json.dumps({'sealed':True,'files':len(hashes),'retry_count':read(B/'resume-plan.json')['retry_count']}))
