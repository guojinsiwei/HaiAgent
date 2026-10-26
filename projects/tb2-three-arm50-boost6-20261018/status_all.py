"""Merge attempts by original budget job; never double-count inherited results."""
import collections,datetime,json,shutil
from pathlib import Path
from recovery import owned_alive
R=Path(__file__).resolve().parent;BASE=R.parent
roots=[BASE/n for n in ['tb2-three-arm50-20261017','tb2-three-arm50-retry-20261018','tb2-three-arm50-retry2-20261018','tb2-three-arm50-boost6-20261018']]
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,ValueError):return {}
merged={};active=[];stages=[]
for root in roots:
 h=read(root/'health.json');alive=owned_alive(h.get('supervisor_identity'));byjob={r['job']:r for r in h.get('rows',[])}
 for row in h.get('rows',[]):
  key=row.get('budget_job',row['job'])
  if root==roots[0] or row.get('engineering_clean'):merged[key]=row
 if alive:
  for a in h.get('active',[]):active.append(dict(**a,arm=byjob[a['job']]['arm'],task=byjob[a['job']]['task']))
 stages.append(dict(root=str(root),state=h.get('state'),alive=alive))
summary={arm:dict(tasks=len(rr),clean=sum(bool(r.get('engineering_clean')) for r in rr),passed=sum(bool(r.get('engineering_clean')) and r.get('result',{}).get('reward')==1 for r in rr)) for arm in ['native-kz','kz-dsh','dsh'] for rr in [[r for r in merged.values() if r['arm']==arm]]}
print(json.dumps(dict(time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),summary=summary,stages=stages,active=active,total_active=len(active),free_GiB=shutil.disk_usage('/var/lib/docker').free/1024**3),ensure_ascii=False))
