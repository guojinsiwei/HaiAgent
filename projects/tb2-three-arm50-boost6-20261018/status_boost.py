import collections,datetime,json,shutil
from pathlib import Path
import boost
from recovery import owned_alive
boost.validate()
out=[];active=[]
for root in (boost.S,boost.R):
 h=boost.read(root/'health.json');alive=owned_alive(h.get('supervisor_identity'))
 out.append(dict(root=str(root),state=h.get('state'),alive=alive,summary=h.get('summary'),spending=h.get('spending')))
 if alive:
  rows={r['job']:r for r in h.get('rows',[])}
  for a in h.get('active',[]):active.append(dict(**a,arm=rows[a['job']]['arm'],task=rows[a['job']]['task'],requests=rows[a['job']].get('live',{}).get('requests')))
print(json.dumps(dict(checked_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),campaigns=out,active=active,total_active=len(active),by_arm=dict(collections.Counter(r['arm'] for r in active)),free_GiB=shutil.disk_usage('/var/lib/docker').free/1024**3),ensure_ascii=False))
