"""Prepare two isolated campaigns; never mutate prior experiments or use a model."""
from pathlib import Path
import collections,hashlib,json,os,random,shutil,subprocess,sys
R=Path(__file__).resolve().parent
H=R.parent
TB=H/'tb2-hld-recuris50-20261020'
AW=H/'appworld-hld-recuris70-20261020'
TEMPLATE=H/'tb2-hld-old-new10-20261019'
TB50=H/'tb2-three-arm50-20261017'
APP=H/'appworld-three-arm30-20261018'
AB=H/'swepro-hld-ab5-20261020'
SWE=H/'swepro-hld-recuris15-20261019'

def read(p):return json.loads(p.read_text())
def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False))
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def cp(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)
def edit(p,a,b):
 s=p.read_text();assert a in s,(str(p),a[:80]);p.write_text(s.replace(a,b))
def tree(a,b):shutil.copytree(a,b,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
def link(a,b):
 b.parent.mkdir(parents=True,exist_ok=True);os.link(a,b)
def seal_sources(base,paths):
 return {str(p.relative_to(base)):digest(p) for folder in paths for p in (base/folder).rglob('*') if p.is_file() and 'node_modules' not in p.parts}

def prep_tb():
 TB.mkdir()
 for p in TEMPLATE.iterdir():
  if p.suffix in ('.py','.mjs') and p.is_file():cp(p,TB/p.name)
 for n in ['agents.py','container-run.mjs']:
  cp(H/'tb4-hld-recuris7-20261019'/n,TB/n)
 edit(TB/'agents.py','hld-v5-tb4','hld-v7-tb2')
 # Stable harness, descriptive labels, exact frozen original 50 tasks.
 for n in ['campaign.py','queue_policy.py','acceptance.py','entry_probe.py']:
  p=TB/n;s=p.read_text().replace("'hld-old'","'hld'").replace("'hld-new'","'recuris'").replace("tb2hld-","tb2hr50-")
  p.write_text(s)
 edit(TB/'campaign.py','PORT=28941','PORT=29051')
 edit(TB/'campaign.py','port=28942','port=29052')
 edit(TB/'campaign.py','total_trials=20','total_trials=100')
 edit(TB/'campaign.py',"hld_monetary_stop(live,'hld',exit_valid,code)","hld_monetary_stop(live,row['arm'],exit_valid,code)")
 edit(TB/'campaign.py',"CAMPAIGN_BUDGET_ARM='kz')","CAMPAIGN_BUDGET_ARM='dsh' if row['arm']=='recuris' else 'kz')")
 edit(TB/'entry_probe.py',"'CAMPAIGN_BUDGET_ARM':'kz'","'CAMPAIGN_BUDGET_ARM':'dsh' if agent.arm=='recuris' else 'kz'")
 edit(TB/'queue_policy.py','!=10','!=50')
 edit(TB/'queue_policy.py','Expected 10','Expected 50')
 edit(TB/'queue_policy.py',"passed=sum(r.get('engineering_clean',False) and r.get('result',{}).get('reward')==1 for r in rr)","passed=sum(r.get('result',{}).get('reward')==1 for r in rr)")
 p=TB/'experiment.py'
 s=p.read_text().replace('original_tb2_sample10_fixed_before_outcomes','reuse_frozen_tb2_sample50_20261017').replace("'task_count':10,'trial_count':20","'task_count':50,'trial_count':100").replace('total_trials=20,max_trials_with_retry=20','total_trials=100,max_trials_with_retry=100').replace('!=10','!=50')
 p.write_text(s)
 manifest=read(TB50/'tasks.json');save(TB/'tasks.json',manifest);save(TB/'history.json',{})
 (TB/'venv').symlink_to(TEMPLATE/'venv',target_is_directory=True)
 link(TEMPLATE/'python-runtime.tar.gz',TB/'python-runtime.tar.gz')
 (TB/'environment-locks').mkdir()
 deps=TB/'dependencies'
 cp(TB50/'dependencies/network_proxy.py',deps/'network_proxy.py')
 for t in manifest['tasks']:tree(TB50/'dependencies/official/tasks'/t['name'],deps/'official/tasks'/t['name'])
 save(deps/'ready.json',{'commit':manifest['commit'],'files':seal_sources(deps,['official','network_proxy.py'])|{'network_proxy.py':digest(deps/'network_proxy.py')}})
 bundle=TB/'bundle';bundle.mkdir()
 tree(AB/'bundle/hld-new',bundle/'kz')
 for n in ['node','recuris-dsh','dsh-baselines']:tree(AB/'bundle'/n,bundle/n)
 # Shared dependencies are immutable; resolve old relative symlinks explicitly.
 for n in ['kz','recuris-dsh','dsh-baselines']:
  p=bundle/n/'node_modules'
  if p.is_symlink():p.unlink()
  if not p.exists():p.symlink_to(TB50/'runtime/kz/node_modules',target_is_directory=True)
 # TB uses the tested CLI entry without SWE-specific socket relay.
 s=(SWE/'bundle/kz/container-run.mjs').read_text()
 s=s.replace("import {relay} from './socket-relay.mjs';\nconst closeRelay=await relay();\n",'').replace('closeRelay();','')
 s=s.replace('wallSeconds:3000','wallSeconds:7200').replace('deadline(child,3000','deadline(child,7200')
 s=s.replace('NO_PROXY:bundle.no_proxy,',"NO_PROXY:bundle.no_proxy+',10.123.0.1',")
 (TB/'container-run.mjs').write_text(s);cp(TB/'container-run.mjs',bundle/'kz/container-run.mjs')
 # Resolve portable dependency modules when archived into /opt.
 for n in ['recuris-dsh','dsh-baselines']:
  p=bundle/n/'node_modules'
  if p.is_symlink():p.unlink()
  p.symlink_to('../kz/node_modules',target_is_directory=True)
 p=bundle/'kz/node_modules'
 if p.is_symlink():
  p.unlink();tree(TB50/'runtime/kz/node_modules',p)
 # Materialize node if source was a symlink outside the archive.
 p=bundle/'node'
 if p.is_symlink():
  source=p.resolve();p.unlink();tree(source,p)
 p=bundle/'kz/.runtime/kz.patch.yml'
 s=p.read_text();assert 'limitCny: 8' in s
 p.write_text(s.replace('wallSeconds: 3000','wallSeconds: 7200'))
 sys.path.insert(0,str(TB))
 from queue_policy import initial_rows
 from experiment import EXPECTED,protocol_fields
 names=[t['name'] for t in manifest['tasks']]
 profile=read(TEMPLATE/'budget-profile.json')
 profile.update(campaign_limit_microcny=800000000,task_limit_microcny=8000000,jobs=[r['job'] for r in initial_rows(names,{})])
 save(TB/'budget-profile.json',profile);save(TB/'experiment.json',EXPECTED)
 proto=dict(benchmark=manifest['benchmark'],commit=manifest['commit'],arms=['hld','recuris'],selection=names,model='deepseek-flash',temperature=0,thinking=False,
  budget=dict(server_solver_seconds=7200,per_run_cny=8,campaign_cny=800,shared_requests=400,shared_tools=600),
  hld_source=str(AB/'bundle/hld-new'),recuris_source=str(AB/'bundle/recuris-dsh'),cross_task_memory=False,
  historical_exposure='Reuses previously tested 50-task list. All current results are fresh, with no prior solver artifacts supplied.')
 proto.update(protocol_fields(EXPECTED));save(TB/'protocol.json',proto)
 for mod in ['queue_policy','experiment']:sys.modules.pop(mod,None)
 sys.path.pop(0)
 # Cache creation is keyless and precedes any paid admission for that task.
 cp(H/'tb2-three-arm50-scorefix-20261018/warm_dependencies.py',TB/'warm_dependencies.py')
 edit(TB/'warm_dependencies.py',"'tb2-scorewarm-'","'tb2hr50-warm-'")
 edit(TB/'warm_dependencies.py',"'kz.scorefix=20261018'","'experiment=tb2-hld-recuris50-20261020'")
 edit(TB/'warm_dependencies.py','timeout=14400','timeout=2400')
 cp(TB50/'verifier-deps.tar.gz',TB/'verifier-deps.tar.gz')
 cp(R/'ensure_cache.py',TB/'ensure_cache.py')
 edit(TB/'agents.py',"  result=await self.exec_as_agent(","  import asyncio,os\n  from ensure_cache import ensure\n  await asyncio.to_thread(ensure,os.environ['PAIRED_TASK'])\n  result=await self.exec_as_agent(")
 save(TB/'algorithm-source-lock.json',seal_sources(bundle,['kz/src','recuris-dsh/src','dsh-baselines/src']))
 # Wait for the small existing paired experiment to finish before adding four slots.
 edit(TB/'campaign.py',"    # Keep 12 GiB free beyond conservative, task-specific concurrent reservations.","    old=read(ROOT.parent/'swepro-hld-ab5-20261020/health.json')\n    if old.get('state')=='running' and old.get('concurrency',0)>0:return False\n    # Keep 12 GiB free beyond conservative, task-specific concurrent reservations.")
 subprocess.run(['tar','-czf',str(TB/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz','recuris-dsh','dsh-baselines'],check=True)
 save(TB/'prepared.json',dict(passed=True,paid_calls=0))
 print('TB prepared',flush=True)

def prep_aw():
 AW.mkdir()
 for n in ['common.py','runtime_helper.py','spending.py','repair_classification.py','grade.py','image.json','test_bounded_ledger.py']:
  cp(APP/n,AW/n)
 cp(APP/'repair-v4/runner.py',AW/'runner.py')
 p=AW/'runner.py';s=p.read_text()
 s=s.replace("sys.path.insert(0,str(Path(__file__).resolve().parent.parent))","sys.path.insert(0,str(Path(__file__).resolve().parent))")
 s=s.replace('R=V.parent','R=V')
 # Retain trial lifecycle and public AppWorld interface; new controller below.
 s=s[:s.index('def validate():')]
 s=s.replace("'version':4","'version':7").replace('repair_version=4','repair_version=7')
 # HLD ceiling is identified by structured terminal event by the current classifier.
 s=s.replace('s=classify(s,d)',"s=classify(s,d)\n        from budget_classification import hld_monetary_stop\n        if hld_monetary_stop(d/'audit',arm,(d/'audit/agent-exit.json').exists(),p.returncode):\n            s['stop_reason']='per_task_budget_exhausted'\n            if s.get('engineering_fault')=='solver_process_error':s.pop('engineering_fault')")
 p.write_text(s)
 cp(TEMPLATE/'budget_classification.py',AW/'budget_classification.py')
 for n in ['client.py','world_server.py','appworld_guard.py','container-run.mjs','entry_acceptance.py']:
  cp(APP/'repair-v5'/n,AW/n)
 p=AW/'entry_acceptance.py'
 edit(p,"['hld','kzdsh-new','recuris']","['hld','recuris']")
 p=AW/'container-run.mjs'
 edit(p,"KZ_APPWORLD:'1',","KZ_APPWORLD:'1',HLD_PLANNER_PROTOCOL:'3',")
 edit(p,"patches.push('/opt/kz/.runtime/kz.patch.yml');","patches.push('/opt/kz/.runtime/kz.patch.yml','/opt/kz/.runtime/hld-new-context.patch.yml');")
 rt=AW/'runtime';rt.mkdir()
 for arm in ['hld','recuris']:
  tree(APP/'repair-v5/runtime'/arm,rt/arm)
 for arm in ['recuris-dsh','dsh-baselines']:
  tree(AB/'bundle'/arm,rt/arm)
 # Only new HLD source changes; the AppWorld adapter/guards remain active.
 for p in (rt/'hld/src').glob('*.mjs'):p.unlink()
 for p in (AB/'bundle/hld-new/src').glob('*.mjs'):cp(p,rt/'hld/src'/p.name)
 cp(AB/'bundle/hld-new/.runtime/hld-new-context.patch.yml',rt/'hld/.runtime/hld-new-context.patch.yml')
 cp(AB/'bundle/hld-new/boot-guard.mjs',rt/'hld/boot-guard.mjs')
 (AW/'assets').symlink_to(APP/'assets',target_is_directory=True)
 (AW/'venv').symlink_to(APP/'venv',target_is_directory=True)
 old=read(APP/'task-manifest.json');oldids={x['task'] for x in old['tasks']}
 allids=[s.strip() for s in (APP/'assets/data/datasets/test_normal.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
 assert len(set(allids))==168 and len(oldids)==30
 # 23 complete new scenarios plus one seeded instance, exactly 70 new tasks.
 groups=collections.defaultdict(list)
 for t in allids:
  if t not in oldids:groups[t.rsplit('_',1)[0]].append(t)
 assert all(len(v)==3 for v in groups.values())
 rng=random.Random(20261020);scenarios=rng.sample(sorted(groups),24)
 ids=[t for sc in scenarios[:23] for t in sorted(groups[sc])]+[rng.choice(sorted(groups[scenarios[23]]))]
 assert len(set(ids))==70 and not oldids.intersection(ids)
 public=AW/'public-data';public.mkdir()
 for n in ['api_docs','base_dbs']:(public/n).symlink_to(APP/'public-data'/n,target_is_directory=True)
 cp(APP/'public-data/version.txt',public/'version.txt')
 rows=[]
 for t in ids:
  src=APP/'assets/data/tasks'/t;dst=public/'tasks'/t
  cp(src/'specs.json',dst/'specs.json');tree(src/'dbs',dst/'dbs')
  d=read(src/'specs.json')
  rows.append(dict(task=t,scenario=t.rsplit('_',1)[0],instruction=d['instruction'],supervisor=d.get('supervisor',d.get('main_user')),datetime=d['datetime']))
 # Bind mounts do not follow symlinks outside the mounted public data directory.
 for n in ['api_docs','base_dbs']:
  source=(public/n).resolve();(public/n).unlink();tree(source,public/n)
 assert not list(public.rglob('ground_truth'))
 save(AW/'task-manifest.json',dict(seed=20261020,split='test_normal',excluded_ids=sorted(oldids),scenarios=scenarios,tasks=rows,
  selection='23 uniformly sampled complete unseen scenarios plus one seeded instance from a 24th; no outcome filtering',
  public_data_hashes=seal_sources(public,['tasks','api_docs','base_dbs'])))
 profile=read(APP/'budget-profile.json')
 profile.update(campaign_limit_microcny=1120000000,task_limit_microcny=8000000,jobs=[a+'--'+r['task'] for r in rows for a in ['hld','recuris']])
 save(AW/'budget-profile.json',profile)
 save(AW/'protocol.json',dict(benchmark='AppWorld',split='test_normal',tasks=rows,arms=['hld','recuris'],trials=140,workers=2,model='deepseek-flash',budget=profile,
  hld_source=str(AB/'bundle/hld-new'),recuris_source=str(AB/'bundle/recuris-dsh'),official_grading=True,cross_task_memory=False,automatic_paid_retries=False,
  aggregation='Report new70 first attempts separately; historical30 retained-pass-after-selective-repairs separately; combined100 is mixed-version cumulative result, not latest-version pass@1.'))
 save(AW/'source-lock.json',seal_sources(rt,['hld/src','recuris-dsh/src','dsh-baselines/src']))
 for n in ['app_campaign.py','app_preflight.py']:cp(R/n,AW/n)
 # Freeze every historical attempt and the selected cumulative record now.
 allrows=[]
 for p in (APP/'jobs').glob('*/health.json'):
  d=read(p)
  if d.get('arm') in ['hld','recuris'] and d.get('task') in oldids:
   d['source_file']=str(p);d['source_sha256']=digest(p);allrows.append(d)
 selected=[]
 for arm in ['hld','recuris']:
  for task in sorted(oldids):
   candidates=[r for r in allrows if r['arm']==arm and r['task']==task and r.get('grading')=='complete']
   assert candidates,(arm,task)
   passed=[r for r in candidates if r.get('official_success') is True]
   final=max(passed or candidates,key=lambda r:r.get('ended',0))
   selected.append(dict(arm=arm,task=task,success=final.get('official_success'),source_file=final['source_file'],source_sha256=final['source_sha256'],attempt_count=sum(r['arm']==arm and r['task']==task for r in allrows),repair_version=final.get('repair_version'),job=final['job']))
 save(R/'historical-appworld30.json',dict(rule='Retain an official pass if any, otherwise latest graded attempt; all attempts preserved',selected=selected,attempts=allrows))
 save(AW/'prepared.json',dict(passed=True,paid_calls=0,tasks=70))
 print('AppWorld prepared',flush=True)

if __name__=='__main__':
 save(R/'authorization.json',dict(per_run_cny=8,total_cny=1920,tb2_cny=800,appworld_cny=1120,paid_runs=240,arms=['hld','recuris'],authorized=True))
 if not TB.exists():prep_tb()
 if not AW.exists():prep_aw()
 save(R/'prepared.json',dict(tb2=str(TB),appworld=str(AW),paid_calls=0))
