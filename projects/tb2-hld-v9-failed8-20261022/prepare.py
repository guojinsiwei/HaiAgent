"""Independent v9 diagnostic rerun on exactly the prior v8 comparison failures."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tarfile,time
R=Path(__file__).resolve().parent
BASE=R.parent/'tb2-hld-mechanism-ab10-20261022'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def edit(n,old,new):
 p=R/n;s=p.read_text();assert old in s,(n,old);p.write_text(s.replace(old,new))

assert not (R/'prepared.json').exists()
health=read(BASE/'health.json');latest={r['task']:r for r in health['rows'] if r['arm']=='hld-new'}
selected=[r for r in latest.values() if r.get('result',{}).get('reward')==0 and r.get('engineering_clean')]
assert len(selected)==8
names=[r['task'] for r in selected]
files=['agents.py','host_agent.py','entry_harbor.py','entry_probe.py','trial_runner.py','lifecycle_guard.py','verifier_setup.py','submission_snapshot.py','storage.py','recovery.py','receipts.py','budget_classification.py','spending.py','ensure_cache.py','warm_dependencies.py','image_readiness.py','campaign.py','launch_private.py']
for n in files:shutil.copy2(BASE/n,R/n)
for n in ['python-runtime.tar.gz','verifier-deps.tar.gz']:os.link(BASE/n,R/n)
(R/'venv').symlink_to(BASE/'venv',target_is_directory=True)
tasks=read(BASE/'tasks.json');tasks['tasks']=[t for t in tasks['tasks'] if t['name'] in names];tasks['selection']='Prior v8 clean failures from the frozen v7/v8 paired10; no new task selection'
save(R/'tasks.json',tasks)
for t in names:
 shutil.copytree(BASE/'dependencies/official/tasks'/t,R/'dependencies/official/tasks'/t)
 dest=R/'dependency-cache'/t;dest.mkdir(parents=True)
 for n in ['dependencies.tar','ready.json']:os.link(BASE/'dependency-cache'/t/n,dest/n)
shutil.copy2(BASE/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
save(R/'dependencies/ready.json',dict(files={p.relative_to(R/'dependencies').as_posix():sha(p) for p in (R/'dependencies').rglob('*') if p.is_file()}))
(R/'environment-locks').mkdir();save(R/'history.json',{})
queue='''from collections import Counter
ARMS=('hld-new',)
TERMINAL={'done','engineering_failure','historical'}
def initial_rows(names,history):
 if len(names)!=8 or len(set(names))!=8:raise ValueError('Expected the eight prior v8 failures')
 return [dict(task=t,arm='hld-new',stage='first',job=f'tb2v9a8-{i+1:02d}-hld-v9-{t}',state='pending') for i,t in enumerate(names)]
def first_finished(rows):return all(r['state'] in TERMINAL or r['state']=='paused_by_user' for r in rows)
def append_retry_batch(rows):return False
def candidates(rows,active_arms):return [r for r in rows if r['state']=='pending'][:max(0,4-len(active_arms))]
def finish(row,result):row.update(result=result,engineering_clean=bool(result.get('engineering_clean')),state='done' if result.get('engineering_clean') else 'engineering_failure')
def summary(rows):return {'hld-v9':dict(total=len(rows),finished=sum(r['state'] in TERMINAL for r in rows),clean=sum(r.get('engineering_clean',False) for r in rows),scored=sum(type(r.get('result',{}).get('reward')) in (int,float) for r in rows),engineering_failures=sum(r['state']=='engineering_failure' for r in rows),passed=sum(r.get('result',{}).get('reward')==1 for r in rows))}
'''
(R/'queue_policy.py').write_text(queue)
capacity='''from pathlib import Path
import json,os,shutil
ROOT=Path(__file__).resolve().parent
def external_rows():return []
def choose(rows,active_arms,external):return [r for r in rows if r['state']=='pending'][:max(0,4-len(active_arms))]
def space_ready(task,active):
 if len(active)>=4:return False
 mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
 return shutil.disk_usage('/var/lib/docker').free>(12+10*(len(active)+1))*2**30 and shutil.disk_usage(ROOT).free>4*2**30 and int(mem['MemAvailable'].split()[0])*1024>12*2**30 and os.getloadavg()[0]<(os.cpu_count() or 1)*.9
'''
(R/'tb_capacity_policy.py').write_text(capacity)
contract=dict(task_count=8,trial_count=8,concurrency=4,solver_seconds=7200,paid_attempts_per_task=1,per_run_cny=8,campaign_cny=64)
save(R/'experiment.json',contract)
(R/'experiment.py').write_text("import json\nfrom pathlib import Path\nEXPECTED="+repr(contract)+"\ndef validate_protocol(root):\n c=json.loads((root/'experiment.json').read_text());p=json.loads((root/'protocol.json').read_text());assert c==EXPECTED and p['experiment']==c\n names=[x['name'] for x in json.loads((root/'tasks.json').read_text())['tasks']];assert len(set(names))==8\n assert p['budget']['server_solver_seconds']==7200 and p['budget']['campaign_cny']==64\n return c\n")
edit('campaign.py','PORT=29321','PORT=29671');edit('campaign.py','29322','29672');edit('campaign.py','total_trials=20','total_trials=8');edit('campaign.py','total_concurrency=8','total_concurrency=4');edit('campaign.py','if len(active)>=8:break','if len(active)>=4:break')
edit('agents.py',"return 'hld-v8-mechanism'","return 'hld-v9-efficiency-candidate'")
for n in ['warm_dependencies.py','ensure_cache.py']:edit(n,'tb2hm10-','tb2v9a8-')
edit('warm_dependencies.py','tb2-hld-mechanism-ab10-20261022',R.name)
from queue_policy import initial_rows
rows=initial_rows(names,{})
save(R/'claimed-pending.json',dict(rows=rows))
profile=read(BASE/'budget-profile.json');profile.update(campaign_limit_microcny=64000000,task_limit_microcny=8000000,jobs=[r['job'] for r in rows]);save(R/'budget-profile.json',profile)
protocol=read(BASE/'protocol.json');protocol.update(arms=['HLD v9 efficiency candidate'],selection=names,paired_tasks=8,total_trials=8,max_trials_with_retry=8,concurrency=dict(total=4,per_arm=4),experiment=contract,historical_baseline_root=str(BASE),historical_baseline_rows=[dict(task=r['task'],job=r['job'],result=r['result']) for r in selected],comparison='Diagnostic historical v8 versus fresh v9; equal 8 CNY/400 requests/600 tools/7200 seconds; no concurrent v8 replay')
protocol['budget']['campaign_cny']=64;save(R/'protocol.json',protocol)
bundle=R/'bundle';bundle.mkdir();subprocess.run(['tar','-xzf',str(BASE/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz'],check=True)
candidate=R/'candidate';candidate.mkdir();subprocess.run(['tar','-xzf',str(R/'candidate-source.tar.gz'),'-C',str(candidate)],check=True)
for n in ['src','scripts','config']:
 target=bundle/'kz'/n
 assert target.resolve().is_relative_to(bundle.resolve())
 shutil.rmtree(target);shutil.copytree(candidate/n,target)
patch=bundle/'kz/.runtime/kz.patch.yml';text=patch.read_text();assert 'efficiencyEnabled' not in text and 'limitCny: 8' in text
text=text.replace('full: true','full: true\n        efficiencyEnabled: true');assert 'efficiencyEnabled: true' in text;patch.write_text(text)
subprocess.run([str(bundle/'node/bin/node'),'--check',str(bundle/'kz/src/plugin.mjs')],check=True)
subprocess.run(['tar','-czf',str(R/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz'],check=True)
save(R/'algorithm-source-lock.json',dict(version='HLD v9 efficiency candidate',candidate_source_sha256=sha(R/'candidate-source.tar.gz'),runtime_sha256=sha(R/'runtime-final.tar.gz'),files={str(p.relative_to(bundle)):sha(p) for p in (bundle/'kz/src').glob('*.mjs')}))
save(R/'prepared.json',dict(passed=True,paid_calls=0,tasks=8,trials=8,per_run_cny=8,campaign_cny=64,runtime_sha256=sha(R/'runtime-final.tar.gz')))
print(json.dumps(dict(prepared=True,tasks=names,paid_calls=0)),flush=True)
