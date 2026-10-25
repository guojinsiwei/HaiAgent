"""One explicit infrastructure repair, allowed only with zero solver API leases."""
import json,os,sqlite3,time
from pathlib import Path
from spending import Ledger
ROOT=Path(__file__).resolve().parent
health=json.loads((ROOT/'health.json').read_text())
for pid in [health['pid']]+[row['pid'] for row in health.get('active',[])]:
    try:os.kill(pid,0)
    except ProcessLookupError:pass
    else:raise RuntimeError('Earlier process still active; wait for official cleanup')
ledger=Ledger(ROOT/'spending.sqlite',json.loads((ROOT/'budget-profile.json').read_text()))
with ledger.db() as db:
    if db.execute("SELECT count(*) FROM calls WHERE arm IN ('kz','dsh')").fetchone()[0]:raise RuntimeError('Cannot replay a solver with any API lease')
history=ROOT/('infrastructure-history-'+str(time.time_ns()));history.mkdir()
for name in ('launch.json','health.json','supervisor.log','error.json','provider-error.json','provider-acceptance.json','jobs','preflight','fixture-ledgers'):
    if (ROOT/name).exists():(ROOT/name).rename(history/name)
for path in ROOT.glob('*.log'):path.rename(history/path.name)
with ledger.db() as db:
    old=db.execute("SELECT value FROM meta WHERE key='halt'").fetchone()
    if old and old[0] not in ('provider_budget','budget_service_unavailable','offline_preflight_failed'):raise RuntimeError('Unexpected halt')
    db.execute("DELETE FROM meta WHERE key='halt'")
(history/'repair-receipt.json').write_text(json.dumps(dict(reason='No solver API lease; fix public instruction path, proxy bypass for local budget, and host stop-file permission',spending_preserved=ledger.status())))
print(json.dumps(dict(prepared=True,spending=ledger.status())))
