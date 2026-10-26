"""Run only after all in-flight old solvers finish and replacements wait at boot."""
from pathlib import Path
import hashlib,json,os,shutil,signal,sqlite3,subprocess,time,sys
R=Path('/mnt/sdb/home/lizh639/appworld-three-arm30-20261018');B=R/'repair-v1';S=B/'stage'
sys.path.insert(0,str(S))
from repair_classification import classify
from repair_plan import make_plan
def read(p):return json.loads(p.read_text())
def save(p,v):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2));tmp.replace(p)
def docker(*args):return subprocess.check_output(['docker',*args],text=True)
assert not (B/'deployed.json').exists()
h=read(R/'health.json');assert h['state']=='running' and h['concurrency']==6
parked=[]
for a in h['active']:
    d=R/'jobs'/(a['arm']+'--'+a['task']);s=read(d/'health.json')
    assert (d/'audit/maintenance-wait.json').exists() and s.get('shared_requests',0)==0, ('still solving',a)
    parked.append((d,s))
con=sqlite3.connect(R/'spending.sqlite',timeout=20)
assert con.execute("select count(*) from calls where state='reserved'").fetchone()[0]==0
for d,s in parked:assert con.execute('select count(*) from calls where job=?',(s['job'],)).fetchone()[0]==0
pid=h['pid'];assert b'runner.py\x00--supervise' in Path(f'/proc/{pid}/cmdline').read_bytes()
save(B/'old-health-at-drain.json',h)
os.kill(pid,signal.SIGTERM)
for _ in range(50):
    p=Path(f'/proc/{pid}/stat')
    if not p.exists() or p.read_text().split()[2]=='Z':break
    time.sleep(.1)
else:raise RuntimeError('Old controller did not stop')
parkdir=B/'parked-zero-call-attempts';parkdir.mkdir()
for d,s in parked:
    networks=set()
    for name in [s['solver'],s['world']]:
        c=json.loads(docker('inspect',name))[0]
        assert c['Config']['Labels']['experiment']==R.name
        networks.update(c['NetworkSettings']['Networks'])
        docker('rm','-f',name)
    for net in networks:
        n=json.loads(docker('network','inspect',net))[0]
        assert n['Labels']['experiment']==R.name and not n['Containers']
        docker('network','rm',net)
    assert d.resolve().parent==(R/'jobs').resolve()
    d.rename(parkdir/d.name)
summaries=[]
for d in (R/'jobs').iterdir():
    if d.is_dir():assert (d/'summary.json').exists(),('unaccounted existing attempt',str(d))
for p in sorted((R/'jobs').glob('*/summary.json')):
    s=classify(read(p),p.parent)
    charged=con.execute("select coalesce(sum(case when state='settled' then actual else reserved end),0) from calls where job=?",(s['job'],)).fetchone()[0]
    s['charged_microcny_at_repair']=charged
    s['actual_budget_exhausted']=charged+387072>8000000
    summaries.append(s)
plan=make_plan(read(R/'protocol.json'),summaries);save(B/'resume-plan.json',plan)
old_profile=read(R/'budget-profile.json');save(B/'original-budget-profile.json',old_profile)
profile=dict(old_profile);profile['jobs']=list(old_profile['jobs'])+[x['row']['_job'] for x in plan['queue'] if '_job' in x['row']]
assert profile['campaign_limit_microcny']==720000000 and profile['task_limit_microcny']==8000000
con.execute('BEGIN IMMEDIATE')
assert json.loads(con.execute("select value from meta where key='profile'").fetchone()[0])==old_profile
con.execute("update meta set value=? where key='profile'",(json.dumps(profile,sort_keys=True),));con.commit();con.close()
save(R/'budget-profile.json',profile)
changes={}
def install(dest,source=None,data=None):
    rel=str(dest.relative_to(R));old=dest.read_bytes() if dest.exists() else None
    if old is not None:
        backup=B/'before'/rel;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(old)
    new=Path(source).read_bytes() if source else data
    tmp=dest.with_suffix(dest.suffix+'.tmp');tmp.write_bytes(new);tmp.replace(dest)
    changes[rel]={'before':hashlib.sha256(old).hexdigest() if old is not None else None,'after':hashlib.sha256(new).hexdigest()}
for name in ['spending.py','repair_classification.py','repair_plan.py','runner_repair.py']:
    install(R/name,S/name)
install(R/'status.py',S/'status_repair.py')
for arm in ['hld','kzdsh-new','recuris','dsh']:
    dest=R/'runtime'/arm
    install(dest/'boot-guard.mjs',B/(arm+'-boot-guard.mjs'))
    install(dest/'spending-client.mjs',S/'spending-client.mjs')
    (dest/'maintenance.pause').unlink()
    if arm in ['hld','kzdsh-new']:
        install(dest/'src/budget.mjs',S/'budget-v1.mjs')
        p=dest/'.runtime/kz.patch.yml';t=p.read_text();assert t.count('inputPerMillion: 2')==1 and 'cacheReadPerMillion' not in t
        t=t.replace('inputPerMillion: 2','inputPerMillion: 2\n          cacheReadPerMillion: 0.04').replace('historical-KZ-20261009-peak-upper-bound','TaoToken-20261018-shared-ledger-cache-aware')
        install(p,data=t.encode())
save(B/'deployed.json',{'time':time.time(),'changes':changes,'retry_count':plan['retry_count'],'unstarted_count':plan['unstarted_count'],'original_pid':pid})
save(R/'health.json',{'state':'repair_acceptance','concurrency':0,'pending':[{'arm':x['arm'],'task':x['row']['task']} for x in plan['queue']]})
print(json.dumps({'deployed':True,'retry_count':plan['retry_count'],'unstarted_count':plan['unstarted_count'],'previous_completed':len(summaries)}))
