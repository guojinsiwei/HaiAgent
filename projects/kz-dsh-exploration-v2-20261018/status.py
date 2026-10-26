"""Read-only paired results and mechanism telemetry; no model requests."""
import collections,json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parent
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,ValueError):return {}
def lines(p):
 if p.exists():
  for s in p.read_text(errors='replace').splitlines():
   try:yield json.loads(s)
   except ValueError:pass
def status():
 h=read(R/'health.json');profile=read(R/'budget-profile.json');charges={}
 if (R/'spending.sqlite').exists():
  with sqlite3.connect('file:'+str(R/'spending.sqlite')+'?mode=ro',uri=True) as db:
   charges={job:dict(requests=n,estimated_cny=settled/1e6,reserved_or_unknown_cny=other/1e6) for job,n,settled,other in db.execute("select job,count(*),sum(case when state='settled' then actual else 0 end),sum(case when state!='settled' then reserved else 0 end) from calls group by job")}
 arms={};details=[]
 for arm in ['baseline','candidate']:
  rows=[]
  for task in read(R/'protocol.json').get('tasks',[]):
   job=arm+'--'+task['task'];d=R/'jobs'/job;s=read(d/'summary.json') or read(d/'health.json');grade=read(R/'grades'/job/'result.json')
   events=[e for f in (d/'audit/kz').glob('*.jsonl') for e in lines(f)]
   count=collections.Counter(e.get('event') for e in events)
   saved=[read(f).get('state',{}) for f in (d/'audit/kz').glob('*.json')]
   episodes=max([count['exploration_episode_start']]+[v.get('episode',{}).get('serial',0) for v in saved])
   learning=collections.Counter(e['record']['status'] for e in events if e.get('event')=='exploration_learning')
   stages=collections.Counter(e.get('role') for e in events if e.get('event')=='role_request')
   row=dict(task=task['task'],arm=arm,state=s.get('state','pending'),grading=grade.get('grading_state'),
    passed=grade.get('official_success'),f2p=grade.get('f2p',{}).get('step_score'),p2p=grade.get('p2p_step_score'),
    cost=charges.get(job),episodes=episodes,learning=dict(learning),
    exploration_rejections=sum(e.get('event')=='proposal' and e.get('result',{}).get('accepted') is False for e in events),
    total_tools=s.get('tools'),solver_seconds=(s.get('ended',s.get('updated',0))-s.get('started',0)) if s.get('started') else None,
    explicit_result_uses=count['exploration_result_used'],role_requests=dict(stages),
    engineering_fault=s.get('engineering_fault'),stop_reason=s.get('stop_reason'))
   rows.append(row);details.append(row)
  scored=[r for r in rows if r['grading']=='complete' and not r['engineering_fault']]
  arms[arm]=dict(finished=sum(r['state'] in ['graded','needs_attention'] for r in rows),valid_scored=len(scored),
   passed=sum(r['passed'] is True for r in scored),mean_f2p=sum(r['f2p'] for r in scored)/len(scored) if scored else None,
   engineering_faults=sum(bool(r['engineering_fault']) for r in rows),
   estimated_cost_cny=sum((r['cost'] or {}).get('estimated_cny',0) for r in rows))
 return dict(state=h.get('state','prepared' if (R/'ready.json').exists() else 'preparing'),concurrency=h.get('concurrency',0),
   budget=h.get('budget'),arms=arms,details=details,
   note='Single run per arm/task on six selected diagnostic tasks. Report paired outcomes and engineering failures; no claim of general significance.')
if __name__=='__main__':print(json.dumps(status(),ensure_ascii=False,indent=2))
