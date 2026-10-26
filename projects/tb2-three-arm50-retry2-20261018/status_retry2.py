import collections,datetime,json
import retry
from recovery import owned_alive
retry.validate()
h=retry.read(retry.R/'health.json')
rows,skipped=retry.select_remaining(retry.read(retry.P/'health.json'))
out=dict(checked_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),eligible=len(rows),by_arm=dict(collections.Counter(r['arm'] for r in rows)),skipped=skipped,schedule=retry.read(retry.R/'schedule.json'),state=h.get('state'),alive=owned_alive(h.get('supervisor_identity')),summary=h.get('summary'),active=h.get('active'),spending=h.get('spending'),rows=[dict(job=r['job'],state=r['state'],requests=r.get('live',{}).get('requests'),result=r.get('result',{})) for r in h.get('rows',[]) if r['state']!='pending'])
print(json.dumps(out,ensure_ascii=False))
