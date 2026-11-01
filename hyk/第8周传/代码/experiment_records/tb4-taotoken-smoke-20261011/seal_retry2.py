import datetime, hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parent
trials=list((root/'jobs/retry2-compaction-acceptance-e').glob('*/result.json'))
assert len(trials)==1
result=json.loads(trials[0].read_text())
checks=json.loads((trials[0].parent/'agent/offline-checks-compaction.json').read_text())
assert result['exception_info'] is None and result['finished_at']
assert checks['exit_code']==0 and checks['compaction_calls']>0 and checks['compaction_accounted']
assert checks['compaction_successes']>0 and not checks['compaction_errors']
assert checks['budget_accounted_requests']==checks['calls']
assert checks['native_tool_result'] and checks['settings_ok'] and checks['kz_tool_present']
assert all(n==8192 for n in checks['compaction_output_caps'])
names=['launch_retry2.py','harbor_retry2.py','route2.patch.yml','compaction-repair.patch.yml','offline_compaction.py',
       'harbor_retry1.py','harbor_kz.py','runtime.tar.gz','route.patch.yml','route-audit.mjs','dsh_runtime.py','container-retry1.py','offline_headless.py']
record={'sealed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'offline_passed':True,'checks':checks,
        'change':'Native compaction maxTokens=8192; original task budget unchanged',
        'sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}}
(root/'retry2-ready.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record,indent=2))
