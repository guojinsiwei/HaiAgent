"""Prepare a separate paired campaign. No model calls; never mutate prior runs."""
from pathlib import Path
import json,shutil,hashlib,os,subprocess
R=Path(__file__).resolve().parent
H=R.parent
OLD=H/'tb4-hld-recuris7-20261019'
TB=H/'tb2-kz-dsh-paired10-20261016'
SCORE=H/'tb2-three-arm50-scorefix-20261018'
def write(n,v):(R/n).write_text(json.dumps(v,indent=2))
def edit(n,a,b):
 p=R/n;s=p.read_text();assert a in s,(n,a);p.write_text(s.replace(a,b))
def main():
 assert not (R/'prepared.json').exists()
 for pattern in ['*.py','*.mjs']:
  for p in OLD.glob(pattern):
   if p.name!='prepare_compare.py':shutil.copy2(p,R/p.name)
 # The harness uses descriptive labels; both run the same DSH substrate.
 edit('queue_policy.py',"ARMS=('hld','recuris')","ARMS=('hld-old','hld-new')")
 edit('queue_policy.py','len(names)!=7','len(names)!=10')
 edit('queue_policy.py','len(set(names))!=7','len(set(names))!=10')
 edit('queue_policy.py','Expected 7 unique','Expected 10 unique')
 edit('queue_policy.py',"f'tb4-","f'tb2hld-")
 edit('campaign.py','PORT=28931','PORT=28941')
 edit('campaign.py','port=28932','port=28942')
 edit('campaign.py',"('HLD' if row['arm']=='hld' else 'Recuris')","('HLD' if row['arm']=='hld-old' else 'Recuris')")
 edit('campaign.py',"row['arm']=='recuris'","row['arm']=='hld-new'")
 edit('campaign.py',"CAMPAIGN_BUDGET_ARM='dsh' if row['arm']=='hld-new' else 'kz'","CAMPAIGN_BUDGET_ARM='kz'")
 edit('campaign.py',"hld_monetary_stop(live,row['arm'],exit_valid,code)","hld_monetary_stop(live,'hld',exit_valid,code)")
 edit('campaign.py','total_trials=14','total_trials=20')
 edit('agents.py',"arm='hld'","arm='hld-old'")
 edit('agents.py',"arm='recuris'","arm='hld-new'")
 edit('agents.py','hld-v5-tb4','hld-v5-tb2-baseline')
 edit('agents.py','recuris-v5-tb4','hld-v6-tb2-candidate')
 edit('entry_probe.py',"'dsh' if agent.arm=='recuris' else 'kz'","'kz'")
 edit('acceptance.py',"['hld','recuris']","['hld-old','hld-new']")
 edit('acceptance.py',"'fin-saccr-rwa'","'build-cython-ext'")
 # Freeze 10 original sample names/content without outcome-based filtering.
 manifest=json.loads((TB/'tasks.json').read_text());write('tasks.json',manifest)
 deps=R/'dependencies';deps.mkdir(exist_ok=True)
 shutil.copy2(OLD/'dependencies/network_proxy.py',deps/'network_proxy.py')
 for t in manifest['tasks']:shutil.copytree(TB/'dependencies/official/tasks'/t['name'],deps/'official/tasks'/t['name'],dirs_exist_ok=True)
 write('dependencies/ready.json',{'commit':manifest['commit'],'files':{str(p.relative_to(deps)):hashlib.sha256(p.read_bytes()).hexdigest() for p in deps.rglob('*') if p.is_file() and p.name!='ready.json' and '__pycache__' not in p.parts}})
 if not (R/'venv').exists():(R/'venv').symlink_to(OLD/'venv',target_is_directory=True)
 if not (R/'python-runtime.tar.gz').exists():os.link(OLD/'python-runtime.tar.gz',R/'python-runtime.tar.gz')
 (R/'environment-locks').mkdir(exist_ok=True)
 # Same official dependency cache, mounted only during verification.
 shutil.copy2(SCORE/'verifier_setup.py',R/'verifier_setup.py')
 for t in manifest['tasks']:
  name=t['name'];kind='pip' if name in ['build-cython-ext','fix-code-vulnerability'] else 'uv'
  base=SCORE/'dependency-cache'/('largest-eigenval' if kind=='pip' else 'mteb-leaderboard')
  cache=R/'dependency-cache'/name;cache.mkdir(parents=True,exist_ok=True)
  if not (cache/'dependencies.tar').exists():
   with (cache/'dependencies.tar').open('wb') as output:
    subprocess.run(['zstd','-d','-c',str(base/'dependencies.tar.zst')],stdout=output,check=True)
  spec=json.loads((base/'ready.json').read_text());spec['test_sha256']=hashlib.sha256((deps/'official/tasks'/name/'tests/test.sh').read_bytes()).hexdigest()
  (cache/'ready.json').write_text(json.dumps(spec,indent=2))
 # Keep immutable old algorithm alongside candidate; dependencies are shared.
 bundle=R/'bundle'
 if not bundle.exists():shutil.copytree(OLD/'runtime',bundle,symlinks=True)
 baseline=bundle/'hld-old';baseline.mkdir(exist_ok=True)
 shutil.copytree(OLD/'runtime/kz/src',baseline/'src',dirs_exist_ok=True)
 shutil.copytree(OLD/'runtime/kz/scripts',baseline/'scripts',dirs_exist_ok=True)
 if not (baseline/'node_modules').exists():(baseline/'node_modules').symlink_to('../kz/node_modules',target_is_directory=True)
 shutil.copytree(R/'runtime/hld/src',bundle/'kz/src',dirs_exist_ok=True)
 patch=(bundle/'kz/.runtime/kz.patch.yml').read_text().replace('limitCny: 6','limitCny: 4')
 (bundle/'kz/.runtime/kz.patch.yml').write_text(patch)
 (bundle/'kz/.runtime/hld-old.patch.yml').write_text(patch.replace('/opt/kz/src/plugin.mjs','/opt/hld-old/src/plugin.mjs'))
 (bundle/'kz/.runtime/hld-new-context.patch.yml').write_text('- id: compaction-basic\n  config:\n    headroomTokens: 16384\n    maxTokens: 4096\n')
 shared=bundle/'kz/shared-budget.mjs';shared.write_text(shared.read_text().replace('estimatePeakCny:6','estimatePeakCny:4'))
 boot=bundle/'kz/boot-guard.mjs';boot.write_text(boot.read_text().replace("['hld','kzdsh-new']","['hld','kzdsh-new','hld-old','hld-new']"))
 s=(R/'container-run.mjs').read_text().replace("['hld','recuris']","['hld-old','hld-new']")
 s=s.replace("HLD_PLANNER_PROTOCOL:'2'","HLD_PLANNER_PROTOCOL:bundle.arm==='hld-new'?'3':'2'")
 s=s.replace("bundle.arm==='recuris'?'dsh':'kz'","'kz'")
 s=s.replace("...(bundle.arm==='hld'?['.runtime/kz.patch.yml']:[])","...(bundle.arm==='hld-old'?['.runtime/hld-old.patch.yml']:['.runtime/kz.patch.yml','.runtime/hld-new-context.patch.yml'])")
 start=s.index("if(bundle.arm==='recuris'){");end=s.index("args.push('--json'",start);s=s[:start]+s[end:]
 (R/'container-run.mjs').write_text(s);shutil.copy2(R/'container-run.mjs',bundle/'kz/container-run.mjs')
 # Generic frozen contract retained from the proven campaign supervisor.
 edit('experiment.py',"'selection':'first_7_text_tasks_from_frozen_tb4_ten'","'selection':'original_tb2_sample10_fixed_before_outcomes'")
 edit('experiment.py',"'task_count':7,'trial_count':14","'task_count':10,'trial_count':20")
 edit('experiment.py','total_trials=14,max_trials_with_retry=14','total_trials=20,max_trials_with_retry=20')
 edit('experiment.py','len(names)!=7 or len(set(names))!=7','len(names)!=10 or len(set(names))!=10')
 from queue_policy import initial_rows
 from experiment import EXPECTED,protocol_fields
 names=[t['name'] for t in manifest['tasks']]
 profile=json.loads((OLD/'budget-profile.json').read_text());profile.update(campaign_limit_microcny=80000000,task_limit_microcny=4000000,jobs=[r['job'] for r in initial_rows(names,{})])
 write('budget-profile.json',profile);write('experiment.json',EXPECTED);write('history.json',{})
 protocol={'benchmark':manifest['benchmark'],'commit':manifest['commit'],'arms':['HLD v5 unchanged algorithm','HLD v6 improved'],'paired_tasks':10,'selection':names,'model':'deepseek-flash','endpoint':profile['endpoint'],'temperature':0,'thinking':False,'budget':{'server_solver_seconds':7200,'per_run_cny':4,'campaign_cny':80,'shared_requests':400,'shared_tools':600},'fresh_container':True,'cross_task_memory':False,'original_official_verifier':True,'submission_snapshot_before_verifier':True,'concurrency_note':'4 total, 2 per arm; task failure does not stop unrelated tasks','comparison_scope':'bundled controller/protocol/context improvements; single paired run per task, no causal component attribution'}
 protocol.update(protocol_fields(EXPECTED));write('protocol.json',protocol)
 write('algorithm-source-lock.json',{arm:{str(p.relative_to(bundle)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (bundle/folder/'src').glob('*.mjs')} for arm,folder in [('hld-old','hld-old'),('hld-new','kz')]})
 subprocess.run(['tar','-czf',str(R/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz','hld-old'],check=True)
 write('prepared.json',{'passed':True,'paid_calls':0,'trials':20,'budget_cny':80})
 print('PREPARED 20 runs, 80 CNY ceiling, no model calls',flush=True)
if __name__=='__main__':main()
