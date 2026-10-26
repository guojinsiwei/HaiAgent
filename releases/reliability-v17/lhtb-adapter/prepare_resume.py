import json
from pathlib import Path
from audit import verify
from prepare import write
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'lhtb-triple25-v161-20260926'
if (HERE / 'health.json').exists() or (HERE / 'prior-results.json').exists():
    raise RuntimeError('Resume preparation already exists')
old_health = json.loads((OLD / 'health.json').read_text())
if old_health['state'] != 'needs_attention' or old_health['active']:
    raise RuntimeError('Old experiment is not quiescent')
rows = json.loads((OLD / 'summary.json').read_text())
carried, failed = [], []
for row in rows:
    report = Path(row['report'])
    if not report.resolve().is_relative_to(OLD / 'runs'):
        raise RuntimeError('Unexpected old report path')
    if verify(report.parent / 'agent/audit.jsonl') != row['audit_chain']:
        raise RuntimeError('Old audit modified')
    if not row.get('exception_info') and row.get('verifier_result') is not None:
        carried.append(dict(row, carried_forward=True, origin_protocol_sha256=old_health['protocol_sha256']))
    else:
        failed.append(row)
if len(carried) != 4 or len(failed) != 2 or any(r['method'] != 'bestfgs' for r in failed):
    raise RuntimeError('Unexpected prior attempt set')
write(HERE / 'prior-results.json', carried)
write(HERE / 'prior-failed-attempts.json', failed)
print(json.dumps({'carried_forward': 4, 'infrastructure_retries': 2, 'unstarted': 30}))
