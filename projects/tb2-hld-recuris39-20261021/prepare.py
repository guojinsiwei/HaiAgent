"""Create an isolated 39-task continuation of the frozen 50-task comparison."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tomllib

R=Path(__file__).resolve().parent
OLD=R.parent/'tb2-hld-recuris50-20261020'
SOURCE=R.parent/'tb2-three-arm50-20261017/official-source'
COMMIT='69671fbaac6d67a7ef0dfec016cc38a64ef7a77c'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 assert not (R/'launch-once.marker').exists()
 assert not (R/'spending.sqlite').exists()
 assert subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()==COMMIT
 assert not subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True).strip()
 old=read(OLD/'tasks.json');prior={t['name'] for t in old['tasks']}
 population=sorted(p.parent.name for p in SOURCE.glob('*/task.toml'))
 names=sorted(set(population)-prior)
 assert old['commit']==COMMIT and len(prior)==50 and len(population)==89 and len(names)==39
 for n in prior:
  for p in (OLD/'dependencies/official/tasks'/n).rglob('*'):
   if p.is_file():assert sha(p)==sha(SOURCE/n/p.relative_to(OLD/'dependencies/official/tasks'/n))
 files=['agents.py','host_agent.py','entry_harbor.py','entry_probe.py','trial_runner.py','lifecycle_guard.py','verifier_setup.py','submission_snapshot.py','storage.py','recovery.py','receipts.py','budget_classification.py','spending.py','ensure_cache.py','warm_dependencies.py','image_readiness.py','container-run.mjs','test_bounded_ledger.py','acceptance.py','seal.py']
 for name in files:shutil.copy2(OLD/name,R/name)
 for name in ['runtime-final.tar.gz','python-runtime.tar.gz','verifier-deps.tar.gz','algorithm-source-lock.json']:
  if not (R/name).exists():shutil.copy2(OLD/name,R/name)
  assert sha(R/name)==sha(OLD/name)
 if not (R/'venv').exists():(R/'venv').symlink_to(OLD/'venv',target_is_directory=True)
 tasks=[]
 for n in names:
  data=tomllib.loads((SOURCE/n/'task.toml').read_text())
  tasks.append(dict(name=n,category=data.get('metadata',{}).get('category'),difficulty=data.get('metadata',{}).get('difficulty'),**{k:data.get(k,{}) for k in ['environment','agent','verifier']}))
  shutil.copytree(SOURCE/n,R/'dependencies/official/tasks'/n,dirs_exist_ok=True)
 shutil.copy2(OLD/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
 save(R/'tasks.json',dict(benchmark='Terminal-Bench 2.0',commit=COMMIT,population=89,selection='Sorted exact complement of frozen 50-task comparison; no result-based selection',tasks=tasks))
 save(R/'coverage.json',dict(previous=sorted(prior),added=names,union=population,overlap=[],previous_root=str(OLD)))
 save(R/'dependencies/ready.json',dict(commit=COMMIT,files={p.relative_to(R/'dependencies').as_posix():sha(p) for p in (R/'dependencies').rglob('*') if p.is_file() and p.name!='ready.json'}))
 save(R/'history.json',{})
 (R/'environment-locks').mkdir(exist_ok=True)
 queue=(OLD/'queue_policy.py').read_text().replace('50','39').replace('tb2hr39-', 'tb2hr39-').replace('>=4','>=8').replace("<2:","<4:")
 (R/'queue_policy.py').write_text(queue)
 exp=(OLD/'experiment.py').read_text().replace('reuse_frozen_tb2_sample50_20261017','complement39_of_frozen50_20261021').replace('100','78').replace('50','39').replace("'concurrency':4","'concurrency':8").replace("'total':4,'per_arm':2","'total':8,'per_arm':4")
 (R/'experiment.py').write_text(exp)
 sys.path.insert(0,str(R))
 from experiment import EXPECTED,protocol_fields
 from queue_policy import initial_rows
 rows=initial_rows(names,{})
 save(R/'claimed-pending.json',dict(rows=rows))
 save(R/'experiment.json',EXPECTED)
 profile=read(OLD/'budget-profile.json');profile.update(campaign_limit_microcny=624000000,task_limit_microcny=8000000,jobs=[r['job'] for r in rows]);save(R/'budget-profile.json',profile)
 protocol=read(OLD/'protocol.json');protocol.update(selection=names,historical_exposure='Remaining 39 official tasks; previous 50 retained separately. No previous solver artifacts provided.',**protocol_fields(EXPECTED));protocol['budget']['campaign_cny']=624
 save(R/'protocol.json',protocol)
 campaign=(OLD/'capacity_campaign.py').read_text().replace('29161','29211').replace('29162','29212').replace("CONTROL=ROOT/'capacity10-20261020'","CONTROL=ROOT").replace('len(active)>=10','len(active)>=8').replace('total_trials=100','total_trials=78').replace('total_concurrency=10','total_concurrency=8')
 campaign=campaign.replace("        for row in rows:\n            if row['arm']=='hld' and row['state']=='pending' and 'hld' not in read(ROOT/'enabled-arms.json').get('arms',[]):row.update(state='paused_by_user',pause_reason='user_recuris_only')\n",'')
 (R/'campaign.py').write_text(campaign)
 for name in ['warm_dependencies.py','ensure_cache.py']:
  p=R/name;p.write_text(p.read_text().replace('tb2hr50-warm-','tb2hr39-warm-').replace('tb2-hld-recuris50-20261020','tb2-hld-recuris39-20261021'))
 p=R/'acceptance.py';p.write_text(p.read_text().replace('build-cython-ext','build-pmars'))
 from warm_dependencies import recipe
 recipes={}
 for n in names:
  try:recipes[n]=recipe(n)
  except Exception as e:recipes[n]=dict(error_type=type(e).__name__,error=str(e))
 save(R/'recipe-precheck.json',recipes)
 # Store old results only in host audit metadata, never in the runtime bundle.
 oldfiles={p.relative_to(OLD).as_posix():sha(p) for p in OLD.rglob('result.json') if 'jobs' in p.parts or 'preflight' in p.parts}
 save(R/'previous-results-lock.json',dict(root=str(OLD),files=oldfiles))
 save(R/'continuation-lock.json',dict(source=str(OLD),runtime_sha256=sha(R/'runtime-final.tar.gz'),python_sha256=sha(R/'python-runtime.tar.gz'),source_lock_sha256=sha(R/'algorithm-source-lock.json'),model=profile['model'],paid_calls=0))
 print(json.dumps(dict(tasks=len(names),trials=len(rows),recipe_errors={k:v for k,v in recipes.items() if 'error' in v},runtime_sha256=sha(R/'runtime-final.tar.gz'))))
if __name__=='__main__':main()
