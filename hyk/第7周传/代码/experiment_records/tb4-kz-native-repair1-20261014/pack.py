import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((ROOT/'audit/offline.json').read_text(encoding='utf-8-sig'))
assert report['passed'] and report['real_model_calls']==0
def include(info):return None if '__pycache__' in Path(info.name).parts or info.name.endswith('.pyc') else info
with tarfile.open(ROOT/'legacy-runtime.tar.gz','w:gz') as t:
    t.add(ROOT/'legacy',arcname='kz-standalone/legacy',filter=include)
    for name in ['solve.py','native_repair.py','anthropic_bridge.py','standalone-run.mjs','deadline.mjs','fixture.py','test_native_repair.py']:
        t.add(ROOT/name,arcname='kz-standalone/'+name)
names=['legacy-runtime.tar.gz','campaign.py','harbor_legacy.py','entry_harbor.py','protocol.json','tasks.json',
       'solve.py','native_repair.py','anthropic_bridge.py','standalone-run.mjs','deadline.mjs','fixture.py',
       'test_native_repair.py','test_campaign.py','test_bridge.py','test_wire_live.py','test_deadline.mjs','offline_accept.py','regression_probe.py',
       'original-source.tar.gz','README.txt','audit/offline.json']
ready=dict(schema=1,offline_passed=True,all_legacy_tests_passed=False,known_baseline_failures=report['baseline_regression']['original']['failures'],
    files={n:sha(ROOT/n) for n in names},original_source_sha256=sha(ROOT/'original-source.tar.gz'),
    local_test_image='sha256:e19976ce9f5d95e3c57a2975e2c2515942553227c56868137b342390a1ee6877')
(ROOT/'ready.json').write_text(json.dumps(ready,indent=2))
with tarfile.open(ROOT/'deployment.tar.gz','w:gz') as t:
    for name in names+['ready.json']:t.add(ROOT/name,arcname=name)
print(json.dumps(dict(packaged=True,files=len(names),deployment_sha256=sha(ROOT/'deployment.tar.gz'),model_calls=0)))
