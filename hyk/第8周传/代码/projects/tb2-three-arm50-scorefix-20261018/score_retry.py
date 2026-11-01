"""22 repairs: one immutable submission regrade plus 21 budget-preserving trials."""
import collections,hashlib,json,os,secrets,sqlite3,subprocess,sys,threading,time
from pathlib import Path
R=Path(__file__).resolve().parent;P=R.parent/'tb2-three-arm50-20261017'
from spending import Ledger,server_for
from recovery import owned_alive
def read(p):return json.loads(Path(p).read_text())
def validate():
 seal=read(R/'scorefix-seal.json');assert seal['tests_passed']
 for n,d in seal['files'].items():
  with (R/n).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==d,'Source drift: '+n
 a=read(R/'acceptance-scoring.json');tasks={r['task'] for r in read(R/'repair-plan.json')}
 assert a['passed'] and {r['task'] for r in a['results']}==tasks and all(r['engineering_clean'] and r['paid_calls']==0 for r in a['results'])
 assert read(R/'budget-profile.json')==read(P/'budget-profile.json')
def make_rows(plan,acceptance):
 rows=[];replay=next(r for r in acceptance['results'] if r['task']=='torch-pipeline-parallelism')
 for old in plan:
  row=dict(task=old['task'],arm=old['arm'],stage='retry',job='scorefix-'+old['budget_job'],budget_job=old['budget_job'],state='pending')
  if old['arm']=='dsh' and old['task']=='torch-pipeline-parallelism':
   row.update(state='done',engineering_clean=True,score_only=True,result={**replay,'score_only':True,'original_trial':old['result']['trial'],'additional_model_calls':0})
  else:
   assert old['result'].get('paid_calls')==0 and old['result'].get('reason')=='preflight_failed','Paid solver must never be replayed'
  rows.append(row)
 assert len(rows)==22 and sum(r['state']=='pending' for r in rows)==21
 return rows
class Budget:
 def __init__(self,*_,**__):
  self.ledger=Ledger(P/'spending.sqlite',read(P/'budget-profile.json'))
  self.token=secrets.token_urlsafe(32);self.url='http://10.123.0.1:28746'
  self.server=server_for(self.ledger,self.token,'10.123.0.1',28746)
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def snapshot(self):return self.ledger.status()
 def close(self):self.server.shutdown();self.server.server_close()
def candidates(rows,active):
 busy=collections.Counter(active);out=[]
 for r in rows:
  if sum(busy.values())>=6:break
  if r['state']=='pending' and busy[r['arm']]<2:out.append(r);busy[r['arm']]+=1
 return out
def supervise():
 validate();rows=make_rows(read(R/'repair-plan.json'),read(R/'acceptance-scoring.json'))
 import campaign
 campaign.validate=validate;campaign.BudgetService=Budget;campaign.PORT=28745
 campaign.initial_rows=lambda *_:rows;campaign.candidates=candidates
 campaign.supervise()
def launch():
 validate();assert not (R/'launch-once.marker').exists()
 for name in ('tb2-three-arm50-20261017','tb2-three-arm50-retry-20261018','tb2-three-arm50-retry2-20261018','tb2-three-arm50-boost6-20261018'):
  assert not owned_alive(read(R.parent/name/'health.json').get('supervisor_identity'))
 bundle=json.loads(sys.stdin.readline());key=bundle.pop('key');assert key.startswith('sk-')
 (R/'launch-once.marker').write_text(str(time.time()))
 with (R/'supervisor.log').open('xb') as log:
  p=subprocess.Popen([str(R/'venv/bin/python'),__file__,'--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=R)
 key='';bundle.clear();time.sleep(2);assert p.poll() is None
 print(json.dumps(dict(pid=p.pid,paid_trial_count=21,score_only_count=1,concurrency=6,original_budget=True)))
if __name__=='__main__':
 if '--launch' in sys.argv:launch()
 elif '--supervise' in sys.argv:supervise()
 else:validate();print('READY')
