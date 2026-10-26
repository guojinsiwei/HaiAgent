"""Recover only pre-solver failures; preserve every failed preflight and ledger."""
from pathlib import Path
import copy,json,sqlite3,time
from recovery import owned_alive,completed_attempt
from storage import atomic_json
R=Path(__file__).resolve().parent
def main():
 h=json.loads((R/'admissions.json').read_text())
 assert h['state']=='drained' and not h['active'] and not owned_alive(h['supervisor_identity'])
 folder=R/'keyless-recovery-20261021';folder.mkdir(exist_ok=False)
 atomic_json(folder/'original-admissions.json',h)
 db=sqlite3.connect('file:'+str(R/'spending.sqlite')+'?mode=ro',uri=True)
 changed=[]
 for row in h['rows']:
  if row['state']!='engineering_failure':continue
  assert row['result'].get('reason')=='preflight_failed' and row['result'].get('paid_calls')==0
  assert row.get('attempt_id') is None and row.get('admission_offline') is True
  assert completed_attempt(R,row,True) is not None
  assert db.execute('SELECT COUNT(*) FROM calls WHERE job=?',(row['job'],)).fetchone()[0]==0
  name='preflight-'+row['job']
  for source in [R/(name+'.log'),R/'preflight'/name]:
   if source.exists():source.rename(folder/source.name)
  archived=copy.deepcopy(row)
  keep={k:row[k] for k in ['task','arm','stage','job']}
  row.clear();row.update(keep,state='pending',keyless_previous_attempt=archived['preflight_attempt_id'])
  changed.append(dict(job=row['job'],prior=archived))
 atomic_json(folder/'recovered.json',dict(rows=changed,paid_repeats=0,time=time.time()))
 h.update(state='reconciled',active=[])
 atomic_json(R/'admissions.json',h);atomic_json(R/'health.json',h)
 if (R/'control.json').exists():(R/'control.json').rename(folder/'control.json')
 print(json.dumps(dict(reset_keyless=len(changed),paid_repeats=0)))
if __name__=='__main__':main()
