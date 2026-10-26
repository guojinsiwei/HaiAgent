import json
from pathlib import Path
root = Path('/mnt/sdb/home/lizh639/lhtb-triple25-v161-20260926')
for trial in (root / 'runs').glob('bestfgs-*/*/agent'):
    print('\nTRIAL', trial.parent.name)
    rows = [json.loads(s) for s in (trial / 'audit.jsonl').read_text().splitlines()]
    for row in rows[-8:]:
        item = {k: row[k] for k in ('seq', 'time', 'event', 'role', 'error_type') if k in row}
        if row['event'] == 'tool_call':
            item['command'] = row['command']
            item['result'] = {k: str(v)[-1400:] for k, v in row['result'].items()}
        print(json.dumps(item))
    for snapshot in (trial / 'host-state').iterdir():
        if snapshot.is_dir():
            for p in snapshot.rglob('*'):
                if p.is_symlink():
                    try:
                        p.resolve()
                    except (OSError, RuntimeError) as e:
                        print('BROKEN_RESOLVE', str(p), type(e).__name__, str(e)[:400])
