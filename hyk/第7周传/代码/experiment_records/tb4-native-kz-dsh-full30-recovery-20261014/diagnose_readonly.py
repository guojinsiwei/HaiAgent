import collections
import json
import re
from pathlib import Path

ROOT = Path('/mnt/sdb/home/lizh639/tb4-native-kz-dsh-full30-recovery-20261014')
def read(p):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
def clean(value):
    text = json.dumps(value, ensure_ascii=False)
    text = re.sub(r'(?i)(bearer\s+|\bsk-)[a-zA-Z0-9._-]+', '[REDACTED]', text)
    return text[:2800]
h = read(ROOT / 'health.json')
counts = collections.Counter()
http = collections.Counter()
failures = collections.Counter()
for row in h['rows']:
    result = row.get('result') or {}
    counts[(row['arm'], row['state'])] += 1
    http.update((result.get('http_status_counts') or (row.get('live') or {}).get('http_status_counts') or {}))
    if row['state']=='engineering_failure':
        failures[(row['arm'], 'preflight' if result.get('reason')=='preflight_failed' else 'quota' if (result.get('http_status_counts') or {}).get('429') else 'other_paid')] += 1
        if row['arm']=='dsh' and result.get('reason')!='preflight_failed':
            print(clean(dict(paid_dsh_failure=row['task'],statuses=result.get('http_status_counts'))))
    t = Path(result['trial']) if result.get('trial') else None
    if not t:
        continue
    official = read(t / 'result.json')
    ex = official.get('exception_info') or {}
    if ex:
        message=ex.get('exception_message','')
        print(clean(dict(task=row['task'], arm=row['arm'], exception=ex.get('exception_type'), message_start=message[:220], message_end=message[-1800:] if row['task']=='freecad-impeller' else '')))
    live = t / 'agent/live'
    if row['arm']=='native-kz' and row['task']=='payments-pipeline-fix':
        for name in ('run-status.json', 'result.json'):
            data = read(live / name)
            print(clean(dict(task=row['task'], file=name, keys=list(data), diagnostic={k:data[k] for k in data if any(x in k.lower() for x in ('error','exception','stop','failure','submitted','unregistered'))})))
        print(clean(dict(task=row['task'], files=[p.name for p in live.iterdir()])))
        for p in (live/'trace').glob('*.jsonl'):
            found=[]
            for line in p.open():
                try: item=json.loads(line)
                except ValueError: continue
                if item.get('event') in ('failure','error','exception','infrastructure_error'):
                    found.append({k:v for k,v in item.items() if k in ('event','category','detail','error_type','error','message','frames','error_frames','errno','filename','operation')})
            if found: print(clean(dict(task=row['task'],file=p.name,failures=found[-3:])))
        p=live/'solver.stderr.log'
        if p.exists():print(clean(dict(task=row['task'],stderr=p.read_text()[-1800:])))
    if row['arm']=='dsh' and row['task'] in ('retro-console-soc','gsea-proteomics','wdm-design'):
        errors = []
        p = live / 'dsh.jsonl'
        if p.exists():
            for line in p.open():
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if item.get('type')=='status' and isinstance(item.get('reason'),dict) and item['reason'].get('kind')=='error':
                    errors.append(item['reason'])
        print(clean(dict(task=row['task'], errors=errors[-3:])))
print(json.dumps({'counts': [{'arm':k[0],'state':k[1],'n':v} for k,v in counts.items()]}))
print(json.dumps({'http':dict(http),'failure_buckets':[dict(arm=k[0],kind=k[1],n=v) for k,v in failures.items()]}))
