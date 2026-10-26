import json
from pathlib import Path
R=Path(__file__).resolve().parent
def read(p):
 try:return json.loads(p.read_text())
 except (ValueError,FileNotFoundError):return {}
h=read(R/'health.json')
if h.get('repaired_utc'):h['updated_utc']=h['repaired_utc']
print(json.dumps({'state':h.get('state','not_started'),'updated_utc':h.get('updated_utc'),'concurrency':len(h.get('active',[])),'arms':h.get('summary',{}),'active':[{**a,'task':next((r['task'] for r in h.get('rows',[]) if r['job']==a['job']),None),'live':next((r.get('live',{}) for r in h.get('rows',[]) if r['job']==a['job']),{})} for a in h.get('active',[])],'budget':h.get('spending',{}),'completed':[{'job':r['job'],'state':r['state'],'reward':r.get('result',{}).get('reward'),'reason':r.get('result',{}).get('reason')} for r in h.get('rows',[]) if r['state'] in ['done','engineering_failure']]},indent=2))
