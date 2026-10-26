"""User-authorized continuation, keeping every earlier actual/uncertain charge."""
import json,os,time
from pathlib import Path
from spending import Ledger
ROOT=Path(__file__).resolve().parent
health=json.loads((ROOT/'health.json').read_text())
assert health['state']=='stopped' and not health['active'] and health['winner'] is None
for pid in [health['pid']]+[row['pid'] for row in health.get('active',[])]:
    try:os.kill(pid,0)
    except ProcessLookupError:pass
    else:raise RuntimeError('Old worker still alive')
ledger=Ledger(ROOT/'spending.sqlite',json.loads((ROOT/'budget-profile.json').read_text()))
before=ledger.status()
assert before['reserved_tokens']==0 and before['halt_reason']=='usage_unavailable'
history=ROOT/('interrupted-history-'+str(time.time_ns()));history.mkdir()
for name in ('launch.json','health.json','supervisor.log','error.json','provider-error.json','provider-acceptance.json','jobs','preflight','fixture-ledgers'):
    if (ROOT/name).exists():(ROOT/name).rename(history/name)
for path in ROOT.glob('*.log'):path.rename(history/path.name)
with ledger.db() as db:db.execute("DELETE FROM meta WHERE key='halt' AND value='usage_unavailable'")
receipt=dict(reason='User explicitly requested restart; retain all earlier charges; absent usage consumes full request ceiling without halting the other arm',before=before,after=ledger.status())
(history/'continuation-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
