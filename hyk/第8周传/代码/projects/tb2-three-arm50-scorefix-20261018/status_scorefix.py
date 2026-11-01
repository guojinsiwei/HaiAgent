import collections,datetime,json,shutil
from pathlib import Path
from recovery import owned_alive
R=Path(__file__).resolve().parent
names=['tb2-three-arm50-20261017','tb2-three-arm50-retry-20261018','tb2-three-arm50-retry2-20261018','tb2-three-arm50-boost6-20261018',R.name]
merged={};active=[];latest={}
for name in names:
 p=R.parent/name/'health.json'
 if not p.exists():continue
 h=json.loads(p.read_text())
 for r in h.get('rows',[]):
  key=r.get('budget_job',r['job'])
  if name==names[0] or r.get('engineering_clean'):merged[key]=r
 if owned_alive(h.get('supervisor_identity')):active+=h.get('active',[])
 if name==R.name:latest=h
summary={arm:dict(tasks=len(rr),clean=sum(bool(r.get('engineering_clean')) for r in rr),passed=sum(bool(r.get('engineering_clean')) and r.get('result',{}).get('reward')==1 for r in rr)) for arm in ['native-kz','kz-dsh','dsh'] for rr in [[r for r in merged.values() if r['arm']==arm]]}
print(json.dumps(dict(time=datetime.datetime.now().isoformat(),state=latest.get('state','not_launched'),overall=summary,repair_summary=latest.get('summary'),active=active,actual_concurrency=len(active),spending=latest.get('spending'),free_GiB=shutil.disk_usage('/var/lib/docker').free/1024**3),ensure_ascii=False))
