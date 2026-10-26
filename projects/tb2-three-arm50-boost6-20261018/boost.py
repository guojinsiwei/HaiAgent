"""Drain old admissions without interrupting children; globally bounded takeover."""
import collections,datetime,hashlib,json,os,secrets,subprocess,sys,threading,time
from pathlib import Path
R=Path(__file__).resolve().parent;S=R.parent/'tb2-three-arm50-retry2-20261018';P=R.parent/'tb2-three-arm50-20261017'
from storage import atomic_json
from recovery import owned_alive,process_identity,completed_attempt
from spending import Ledger,server_for
TERMINAL={'done','engineering_failure','historical'}
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,ValueError):return {}
def validate():
 seal=read(R/'boost-seal.json');assert seal.get('tests_passed')
 for name,digest in seal['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,'Source drift '+name
 for name,digest in read(S/'retry-seal.json')['files'].items():assert hashlib.sha256((S/name).read_bytes()).hexdigest()==digest,'Old source drift '+name
 assert read(P/'budget-profile.json')==read(R/'budget-profile.json')
def accepted_old(h,identity):
 return h.get('supervisor_identity')==identity and h.get('state') in ('draining','drained','finished')
def make_rows(h):
 rows=[]
 active={r['job'] for r in h.get('active',[])}
 for old in h['rows']:
  if old['state'] in TERMINAL:continue
  rows.append(dict(task=old['task'],arm=old['arm'],stage='retry',job='boost-'+old['job'],budget_job=old['budget_job'],previous_job=old['job'],state='waiting_previous' if old['job'] in active else 'pending'))
 return rows
def select(rows,new_active,old_health,receipt=lambda r:True):
 by_job={r['job']:r for r in old_health['rows']};active={r['job'] for r in old_health.get('active',[])}
 for row in rows:
  if row['state']!='waiting_previous':continue
  old=by_job[row['previous_job']]
  if old['job'] in active:continue
  if old['state'] in TERMINAL:
   row.update(state='historical',engineering_clean=old.get('engineering_clean',False),result=old.get('result',{}),inherited=True)
  elif old['state']=='pending' and receipt(old):row['state']='pending'
 busy=collections.Counter(new_active)
 for job in active:busy[by_job[job]['arm']]+=1
 selected=[]
 for row in rows:
  if sum(busy.values())>=6:break
  if row['state']=='pending' and busy[row['arm']]<2:selected.append(row);busy[row['arm']]+=1
 return selected
class Budget:
 def __init__(self,*_,**__):
  self.ledger=Ledger(P/'spending.sqlite',read(P/'budget-profile.json'))
  self.token=secrets.token_urlsafe(32);self.url='http://10.123.0.1:28736'
  self.server=server_for(self.ledger,self.token,'10.123.0.1',28736)
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def snapshot(self):return self.ledger.status()
 def close(self):self.server.shutdown();self.server.server_close()
def supervise():
 validate();transfer=read(R/'handover.json');identity=transfer['old_identity']
 while True:
  h=read(S/'health.json')
  if accepted_old(h,identity):break
  atomic_json(R/'handover-status.json',dict(state='waiting_old_drain_ack',supervisor_identity=process_identity(os.getpid())))
  time.sleep(5)
 rows=make_rows(h);atomic_json(R/'handover-snapshot.json',h)
 atomic_json(R/'handover-status.json',dict(state='running',supervisor_identity=process_identity(os.getpid()),inherited_active=h.get('active',[]),total_concurrency=6,per_arm=2))
 import campaign
 campaign.validate=validate;campaign.BudgetService=Budget;campaign.PORT=28735
 campaign.initial_rows=lambda *_:rows
 def candidates(current,new_active):
  old=read(S/'health.json')
  if not accepted_old(old,identity):return []
  return select(current,new_active,old,lambda r:completed_attempt(S,r,True) is not None)
 campaign.candidates=candidates;campaign.supervise()
def launch():
 validate();h=read(S/'health.json');identity=h['supervisor_identity']
 assert owned_alive(identity),'Old supervisor no longer live; inspect before alternate launch'
 assert not (R/'launch-once.marker').exists(),'Already launched'
 raw=Path('/proc')/str(identity['pid'])/'environ'
 # Only extract the existing authorized provider credential; never print/store it.
 entries=raw.read_bytes().split(b'\0');matches=[e.split(b'=',1)[1] for e in entries if e.startswith(b'TAOTOKEN_API_KEY=')]
 assert len(matches)==1 and matches[0].startswith(b'sk-');key=matches[0].decode();entries.clear();matches.clear()
 assert owned_alive(identity),'Old process identity changed'
 atomic_json(R/'handover.json',dict(old_identity=identity,budget_database=str(P/'spending.sqlite'),total_concurrency=6,per_arm=2))
 (R/'launch-once.marker').write_text(str(time.time()))
 with (R/'supervisor.log').open('xb') as log:
  p=subprocess.Popen([str(R/'venv/bin/python'),__file__,'--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=R)
 key='';time.sleep(2);assert p.poll() is None,'New supervisor failed before drain'
 atomic_json(S/'control.json',dict(command='drain',supervisor_identity=identity,reason='User authorized concurrency 6; preserve current children and transfer pending queue'))
 print(json.dumps(dict(new_pid=p.pid,old_identity=identity,old_tasks_untouched=True,total_concurrency=6)))
if __name__=='__main__':
 if '--launch' in sys.argv:launch()
 elif '--supervise' in sys.argv:supervise()
 else:validate();print('BOOST_READY')
