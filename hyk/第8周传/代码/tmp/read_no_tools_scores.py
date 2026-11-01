import json,time
from pathlib import Path
root=Path('/mnt/sdb/home/lizh639/longcli-dh-tools-ablation40-repair1-20261008')
def read(p):return json.loads(p.read_text()) if p.exists() else {}
h=read(root/'health.json')
rows=[]
for job in h.get('completed',[]):
    s=read(root/'jobs'/job/'summary.json');g=read(root/'grades'/job/'result.json')
    rows.append({'task':s.get('task',job.split('--')[-1]),'score':g.get('f2p',{}).get('step_score'),
                 'grading_state':g.get('grading_state'),'full_pass':g.get('official_success'),
                 'p2p_pass':g.get('p2p_is_pass'),'tools':s.get('tool_calls'),
                 'stop_reason':s.get('stop_reason'),'error_type':s.get('error_type')})
print(json.dumps({'observed':time.time(),'state':h.get('state'),'completed':rows,
                  'active':h.get('active'),'pending':h.get('pending'),'fatal':h.get('fatal')},ensure_ascii=False))
