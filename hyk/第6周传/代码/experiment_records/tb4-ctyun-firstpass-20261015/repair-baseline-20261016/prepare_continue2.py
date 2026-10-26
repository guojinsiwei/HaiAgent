"""Continue from the task whose unpaid build failed; retain all spending."""
import json,os,time
from pathlib import Path
from spending import Ledger
ROOT=Path(__file__).resolve().parent
health=json.loads((ROOT/'health.json').read_text())
assert health['state']=='stopped' and health['stop_reason']=='offline_preflight_failed' and not health['active'] and health['winner'] is None
for pid in [health['pid']]+[row['pid'] for row in health.get('active',[])]:
    try:os.kill(pid,0)
    except ProcessLookupError:pass
    else:raise RuntimeError('Old worker still alive')
rows=health['rows'];assert len(rows)==4
assert all(row['task']=='payments-pipeline-fix' and row['state']=='finished' and row['result']['passed'] is False for row in rows[:2])
assert all(row['task']=='layout-config-recreation' and row['state']=='preflight_complete' and row['preflight']['install_ok'] is False for row in rows[2:])
ledger=Ledger(ROOT/'spending.sqlite',json.loads((ROOT/'budget-profile.json').read_text()))
before=ledger.status();assert before['reserved_tokens']==0 and before['halt_reason']=='offline_preflight_failed'
with ledger.db() as db:
    assert db.execute("SELECT count(*) FROM calls WHERE job LIKE '02-%'").fetchone()[0]==0
history=ROOT/('build-interrupted-history-'+str(time.time_ns()));history.mkdir()
for name in ('launch.json','health.json','supervisor.log','error.json','provider-error.json','provider-acceptance.json','jobs','preflight','fixture-ledgers','launch-options.json'):
    if (ROOT/name).exists():(ROOT/name).rename(history/name)
for path in ROOT.glob('*.log'):path.rename(history/path.name)
with ledger.db() as db:db.execute("DELETE FROM meta WHERE key='halt' AND value='offline_preflight_failed'")
(ROOT/'launch-options.json').write_text(json.dumps({'start_index':1}))
receipt=dict(reason='Resume frozen task 2 after unpaid concurrent Docker build snapshot race; task 1 results retained',before=before,after=ledger.status())
(history/'continuation-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
