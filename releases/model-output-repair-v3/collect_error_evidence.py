"""Read completed trial events and export minimal ordered metadata for replay."""
import hashlib
import json
from pathlib import Path

ROOT = Path('/var/tmp/lizh639-lhtb-paired6-repair-v2-20260929')
TARGET = Path('/var/tmp/lizh639-model-output-evidence-20260930.json')
rows = json.loads((ROOT/'summary-v2.json').read_text())
records = []
for row in rows:
    if row['method'] != 'bestfgs':
        continue
    folder = Path(row['report']).parent/'agent'
    audit = folder/'audit.jsonl'
    method = folder/'method/events.jsonl'
    original = [json.loads(line) for line in audit.read_text().splitlines()]
    inner = [json.loads(line) for line in method.read_text().splitlines()]
    events = []
    for event in original:
        if event['event'] not in {'model_error', 'model_response', 'method_end', 'adapter_error', 'mechanism_utilization'}:
            continue
        entry = {key: event[key] for key in ('event', 'role', 'error_code', 'error_type', 'seq', 'time') if key in event}
        if event['event'] == 'method_end':
            entry['result'] = dict(stop_reason=(event.get('result') or {}).get('stop_reason'))
        events.append(entry)
    records.append(dict(task=row['task'], original_classification=row['classification'],
        result={key:row[key] for key in ('method', 'process_exit_code', 'verifier_result', 'exception_info')},
        events=events, inner_errors=[{key:e[key] for key in ('event', 'role', 'error_code', 'failure_kind', 'time') if key in e}
            for e in inner if e['event']=='model_error'],
        audit_path=str(audit), audit_sha256=hashlib.sha256(audit.read_bytes()).hexdigest(),
        method_audit_sha256=hashlib.sha256(method.read_bytes()).hexdigest()))
with TARGET.open('x') as stream:
    json.dump(dict(source=str(ROOT), scope='Metadata replay; original scores/logs unchanged', records=records), stream, indent=2)
print(json.dumps(dict(path=str(TARGET), trials=len(records), bytes=TARGET.stat().st_size)))
