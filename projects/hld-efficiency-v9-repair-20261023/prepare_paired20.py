"""Prepare authorized 40-trial V8/V9.1 pilot, with no model calls."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tarfile,random
B=Path('/mnt/sdb/home/lizh639')
R=B/'tb2-hld-v8-v91-paired20-20261023'
BASE=B/'tb2-hld-mechanism-ab10-20261022'
MORE=B/'tb2-hld-recuris39-20261021'
CAND=B/'hld-efficiency-v9-repair-20261023'
REPAIR=B/'transport-recovery-20261023'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def edit(n,a,b):
 p=R/n;s=p.read_text();assert a in s,(n,a);p.write_text(s.replace(a,b))

assert not R.exists();R.mkdir();(R/'PAID_START_HOLD').write_text('Awaiting offline acceptance; budget authorized 320 CNY / 40 trials')
proposal=read(CAND/'experiment-proposal.json')
proposal.update(status='authorized_preparing',repetitions_per_arm_task=1,total_trials=40,proposed_total_cny=320,paid_launch_authorized=True)
names=sum([proposal[k] for k in ['historical_success_tasks','historical_budget_failure_tasks','historical_other_failure_tasks']],[])
assert len(set(names))==20
random.Random(20261023).shuffle(names)
save(R/'experiment-proposal.json',proposal)
files=['agents.py','host_agent.py','entry_harbor.py','entry_probe.py','trial_runner.py','lifecycle_guard.py','verifier_setup.py','submission_snapshot.py','storage.py','recovery.py','receipts.py','budget_classification.py','spending.py','ensure_cache.py','warm_dependencies.py','image_readiness.py','campaign.py','launch_private.py']
for n in files:shutil.copy2(BASE/n,R/n)
for n in ['python-runtime.tar.gz','verifier-deps.tar.gz']:os.link(BASE/n,R/n)
(R/'venv').symlink_to(BASE/'venv',target_is_directory=True)
sources={t['name']:(p,t) for p in [MORE,BASE] for t in read(p/'tasks.json')['tasks']}
tasks=read(BASE/'tasks.json');tasks.update(selection='Prespecified mixed success/failure regression pilot, seed 20261023',tasks=[sources[n][1] for n in names])
save(R/'tasks.json',tasks)
for n in names:
 p,_=sources[n];shutil.copytree(p/'dependencies/official/tasks'/n,R/'dependencies/official/tasks'/n)
 dest=R/'dependency-cache'/n;dest.mkdir(parents=True)
 for f in ['dependencies.tar','ready.json']:os.link(p/'dependency-cache'/n/f,dest/f)
 assert sha(dest/'dependencies.tar')==read(dest/'ready.json')['archive_sha256']
shutil.copy2(BASE/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
shutil.copy2(REPAIR/'model_proxy.py',R/'model_proxy.py')
edit('dependencies/network_proxy.py','def connect(host,port):',"def connect(host,port):\n    if host=='api.taotoken.net' and port==443:\n        from model_proxy import connect as stable_connect\n        return stable_connect(host,port)")
save(R/'dependencies/ready.json',dict(files={p.relative_to(R/'dependencies').as_posix():sha(p) for p in (R/'dependencies').rglob('*') if p.is_file()}))
(R/'environment-locks').mkdir();save(R/'history.json',{})
q=(BASE/'queue_policy.py').read_text().replace('len(names)!=10','len(names)!=20').replace('len(set(names))!=10','len(set(names))!=20').replace('Expected 10 unique frozen tasks','Expected 20 unique frozen tasks').replace('tb2hm10-','tb2v891-').replace('>=8','>=4').replace("busy[r['arm']]<4","busy[r['arm']]<2")
(R/'queue_policy.py').write_text(q)
capacity='''from pathlib import Path
import os,shutil
from queue_policy import candidates
def external_rows():return []
def choose(rows,active_arms,external):return candidates(rows,active_arms)
def space_ready(task,active):
 if len(active)>=4:return False
 mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
 return shutil.disk_usage('/var/lib/docker').free>(12+15*(len(active)+1))*2**30 and shutil.disk_usage(Path(__file__).parent).free>4*2**30 and int(mem['MemAvailable'].split()[0])*1024>12*2**30 and os.getloadavg()[0]<(os.cpu_count() or 1)*.9
'''
(R/'tb_capacity_policy.py').write_text(capacity)
contract=dict(task_count=20,trial_count=40,concurrency=4,solver_seconds=7200,paid_attempts_per_arm_task=1,per_run_cny=8,campaign_cny=320)
save(R/'experiment.json',contract)
(R/'experiment.py').write_text("import json\nEXPECTED="+repr(contract)+"\ndef validate_protocol(root):\n c=json.loads((root/'experiment.json').read_text());p=json.loads((root/'protocol.json').read_text());assert c==EXPECTED and p['experiment']==c\n names=[x['name'] for x in json.loads((root/'tasks.json').read_text())['tasks']];assert len(set(names))==20\n assert p['budget']['server_solver_seconds']==7200 and p['budget']['campaign_cny']==320\n return c\n")
edit('campaign.py','PORT=29321','PORT=29731');edit('campaign.py','29322','29732')
edit('campaign.py','total_trials=20','total_trials=40');edit('campaign.py','total_concurrency=8','total_concurrency=4');edit('campaign.py','if len(active)>=8:break','if len(active)>=4:break')
edit('campaign.py',"def precheck(resume=False):","def precheck(resume=False):\n    if (ROOT/'PAID_START_HOLD').exists():raise RuntimeError('Offline acceptance or authorization hold')")
edit('agents.py',"return 'hld-v7-frozen'","return 'hld-v8-frozen'");edit('agents.py',"return 'hld-v8-mechanism'","return 'hld-v91-efficiency-repair'")
for n in ['warm_dependencies.py','ensure_cache.py']:edit(n,'tb2hm10-','tb2v891-')
edit('warm_dependencies.py','tb2-hld-mechanism-ab10-20261022',R.name)
import sys;sys.path.insert(0,str(R))
from queue_policy import initial_rows
rows=initial_rows(names,{})
save(R/'claimed-pending.json',dict(rows=rows))
profile=read(BASE/'budget-profile.json');profile.update(campaign_limit_microcny=320000000,jobs=[r['job'] for r in rows]);save(R/'budget-profile.json',profile)
protocol=read(BASE/'protocol.json');protocol.update(arms=['HLD v8 frozen','HLD v9.1 efficiency repair'],selection=names,paired_tasks=20,total_trials=40,max_trials_with_retry=40,concurrency=dict(total=4,per_arm=2),experiment=contract,comparison='Contemporaneous paired fresh runs, one per version/task; all roles included; original results preserved')
protocol['budget']['campaign_cny']=320;save(R/'protocol.json',protocol)
bundle=R/'bundle';bundle.mkdir()
subprocess.run(['tar','-xzf',str(BASE/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz'],check=True)
# Freeze V8 from the actual prior new arm, not the historical V7 old arm.
shutil.copytree(BASE/'bundle/kz/src',bundle/'hld-old/src')
shutil.copy2(BASE/'bundle/kz/package.json',bundle/'hld-old/package.json')
(bundle/'hld-old/node_modules').symlink_to('../kz/node_modules',target_is_directory=True)
for n in ['src','scripts','config']:
 target=bundle/'kz'/n
 assert target.resolve().is_relative_to(bundle.resolve())
 shutil.rmtree(target);shutil.copytree(CAND/'candidate'/n,target)
for n in ['provider-guard.mjs','spending-client.mjs','messages-protocol.mjs']:shutil.copy2(REPAIR/n,bundle/'kz'/n)
shutil.copy2(CAND/'candidate/package.json',bundle/'kz/package.json')
patch=(BASE/'bundle/kz/.runtime/kz.patch.yml').read_text();assert 'efficiencyEnabled' not in patch
(bundle/'kz/.runtime/hld-old.patch.yml').write_text(patch.replace('/opt/kz/src/plugin.mjs','/opt/hld-old/src/plugin.mjs'))
(bundle/'kz/.runtime/kz.patch.yml').write_text(patch.replace('full: true','full: true\n        efficiencyEnabled: true'))
# Keep all other route, shell receipt, context, budget and transport patches identical.
subprocess.run([str(bundle/'node/bin/node'),'--check',str(bundle/'kz/src/full-integration.mjs')],check=True)
subprocess.run(['tar','-czf',str(R/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz','hld-old'],check=True)
v8={p.name:sha(p) for p in (bundle/'hld-old/src').glob('*.mjs')}
assert v8=={p.name:sha(p) for p in (BASE/'bundle/kz/src').glob('*.mjs')}
v91={p.name:sha(p) for p in (bundle/'kz/src').glob('*.mjs')}
assert v91=={p.name:sha(p) for p in (CAND/'candidate/src').glob('*.mjs')}
save(R/'algorithm-source-lock.json',dict(v8=v8,v91=v91,runtime_sha256=sha(R/'runtime-final.tar.gz'),common_transport=[{'name':n,'sha256':sha(bundle/'kz'/n)} for n in ['provider-guard.mjs','spending-client.mjs','messages-protocol.mjs']]))
save(R/'prepared.json',dict(passed=True,paid_calls=0,tasks=20,trials=40,per_run_cny=8,campaign_cny=320,runtime_sha256=sha(R/'runtime-final.tar.gz')))
print(json.dumps(dict(prepared=True,task_order=names,paid_calls=0,cache_archives_verified=20,v8_source_exact=True,v91_source_exact=True)))

