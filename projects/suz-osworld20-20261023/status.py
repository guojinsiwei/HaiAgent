"""Read-only experiment status; no inference or scheduled GPT calls."""
from pathlib import Path
import json,sqlite3,subprocess,time,sys
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'SUZ-repair1'))
from python.outcomes import classify
output={'checked_at':time.time(),'arms':{},'pairs':{},'preflight':{}}
for marker in ['bootstrap','vm','docker-image','protocol','gui']:
    output['preflight'][marker]=(root/'logs'/f'{marker}.ready').exists()
for mode in ['opencua_baseline','suz']:
    runs=list((root/'runs'/mode).glob('*/run-config.json'))
    outcomes=[json.loads(path.read_text()) for path in (root/'runs'/mode).glob('*/result.json')]
    output['arms'][mode]={'started':len(runs),'finished':len(outcomes),
        'scored':sum(o.get('official_score') is not None for o in outcomes),
        'passed':sum(o.get('official_score')==1 for o in outcomes),
        'engineering_errors':sum(classify(o)=='engineering_failure' for o in outcomes)}
for path in (root/'pairs').glob('*/status.json'):
    row=json.loads(path.read_text());output['pairs'][row['id']]={k:row.get(k) for k in ['stage','error','preserved_container'] if row.get(k) is not None}
if (root/'budget.sqlite').exists():
    with sqlite3.connect('file:'+str(root/'budget.sqlite')+'?mode=ro',uri=True) as db:
        output['accounted_cny']=db.execute('select coalesce(sum(charge),0) from calls').fetchone()[0]
        output['usage_by_status']=db.execute('select status,count(*),sum(charge) from calls group by status').fetchall()
output['containers']=subprocess.check_output(['docker','ps','--filter','label=experiment=suz-osworld20-20261023',
    '--format','{{.ID}} {{.Status}}'],text=True).splitlines()
output['repair1']=json.loads(subprocess.check_output([sys.executable,str(root/'repair-status.py')],text=True))
print(json.dumps(output,indent=2))
