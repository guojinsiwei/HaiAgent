"""Apply exactly the same new rules to original DH/RAW traces, not old rates."""
import base64
import gzip
import json
from pathlib import Path
from audit_behavior import main

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'longcli-dh-raw-full20-20261004'
report=json.loads((OLD/'contextual-audit-v2/summary.json').read_text(encoding='utf-8'))
groups=[]
for method,name in [('dh','DH 原版 v9'),('raw','RAW（参考）')]:
    rows=[]
    for row in report['arms'][method]['rows']:
        task=row['task'];folder=OLD/'received'/(method+'--'+task)
        if method=='raw' and task=='cs61_fa24_scheme':folder=OLD/'network-retry/raw--cs61_fa24_scheme'
        rows.append(dict(task=task,scored=True,tools=row['counts']['total'],audit_folder=str(folder)))
    groups.append(dict(name=name,method=method,budget='small',rows=rows))
result=main(dict(site='local',snapshot={'groups':groups}))
print(base64.b64encode(gzip.compress(json.dumps(result,ensure_ascii=False).encode())).decode())
