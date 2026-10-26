"""Resume frozen task 3 after preserving two official failures and the ledger."""
import json, os, time
from pathlib import Path

from spending import Ledger

ROOT = Path(__file__).resolve().parent
health = json.loads((ROOT / 'health.json').read_text())
assert health['state'] == 'stopped'
assert health['stop_reason'] == 'insufficient_disk_for_pair'
assert not health['active'] and health['winner'] is None
try:
    os.kill(health['pid'], 0)
except ProcessLookupError:
    pass
else:
    raise RuntimeError('Old worker still alive')

rows = health['rows']
assert len(rows) == 4
assert {row['arm'] for row in rows[:2]} == {'kz', 'dsh'}
assert all(row['task'] == 'layout-config-recreation' and row['state'] == 'finished'
           and row['result']['passed'] is False and row['result']['reward'] == 0.0
           for row in rows[:2])
assert {row['arm'] for row in rows[2:]} == {'kz', 'dsh'}
assert all(row['task'] == 'fin-saccr-rwa' and row['state'] == 'pending' for row in rows[2:])

ledger = Ledger(ROOT / 'spending.sqlite', json.loads((ROOT / 'budget-profile.json').read_text()))
before = ledger.status()
assert before['reserved_tokens'] == 0 and before['halt_reason'] == 'insufficient_disk_for_pair'
with ledger.db() as db:
    assert db.execute("SELECT count(*) FROM calls WHERE job LIKE '03-%'").fetchone()[0] == 0

history = ROOT / ('task2-complete-history-' + str(time.time_ns()))
history.mkdir()
for name in ('launch.json', 'health.json', 'supervisor.log', 'error.json',
             'provider-error.json', 'provider-acceptance.json', 'jobs',
             'preflight', 'fixture-ledgers', 'launch-options.json'):
    if (ROOT / name).exists():
        (ROOT / name).rename(history / name)
for path in ROOT.glob('*.log'):
    path.rename(history / path.name)
with ledger.db() as db:
    db.execute("DELETE FROM meta WHERE key='halt' AND value='insufficient_disk_for_pair'")
(ROOT / 'launch-options.json').write_text(json.dumps({'start_index': 2}))
receipt = dict(reason='Resume frozen task 3 after two official task-2 failures and disk cache cleanup',
               before=before, after=ledger.status())
(history / 'continuation-receipt.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
