"""Isolated paired mechanism experiment. Offline preparation only."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tomllib
R=Path(__file__).resolve().parent
H=R.parent
BASE=H/'tb2-hld-recuris39-20261021'
TB50=H/'tb2-hld-recuris50-20261020'
SOURCE=H/'tb2-three-arm50-20261017/official-source'
COMMIT='69671fbaac6d67a7ef0dfec016cc38a64ef7a77c'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def edit(name,old,new):
 p=R/name;s=p.read_text();assert old in s,(name,old);p.write_text(s.replace(old,new))
def main():
 assert not (R/'prepared.json').exists() and not (R/'launch-once.marker').exists()
 assert subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()==COMMIT
 assert not subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True).strip()
 selection=read(R/'selection.json');names=[x['task'] for x in selection['tasks']]
 assert len(set(names))==10 and selection['budget']['campaign_cny']==160
 files=['agents.py','host_agent.py','entry_harbor.py','entry_probe.py','trial_runner.py','lifecycle_guard.py','verifier_setup.py','submission_snapshot.py','storage.py','recovery.py','receipts.py','budget_classification.py','spending.py','ensure_cache.py','warm_dependencies.py','image_readiness.py','test_bounded_ledger.py','acceptance.py','seal.py','campaign.py','queue_policy.py','experiment.py','tb_capacity_policy.py','launch_private.py']
 for name in files:shutil.copy2(BASE/name,R/name)
 for name in ['python-runtime.tar.gz','verifier-deps.tar.gz']:
  if not (R/name).exists():os.link(BASE/name,R/name)
 (R/'venv').symlink_to(BASE/'venv',target_is_directory=True)
 tasks=[]
 for name in names:
  data=tomllib.loads((SOURCE/name/'task.toml').read_text())
  tasks.append(dict(name=name,category=data.get('metadata',{}).get('category'),difficulty=data.get('metadata',{}).get('difficulty'),**{k:data.get(k,{}) for k in ['environment','agent','verifier']}))
  shutil.copytree(SOURCE/name,R/'dependencies/official/tasks'/name)
  candidates=[TB50/'dependency-cache'/name,BASE/'dependency-cache'/name]
  cache=next(p for p in candidates if (p/'ready.json').exists() and (p/'dependencies.tar').exists())
  spec=read(cache/'ready.json');assert spec['test_sha256']==sha(SOURCE/name/'tests/test.sh')
  assert spec['archive_sha256']==sha(cache/'dependencies.tar')
  dest=R/'dependency-cache'/name;dest.mkdir(parents=True)
  os.link(cache/'dependencies.tar',dest/'dependencies.tar');shutil.copy2(cache/'ready.json',dest/'ready.json')
  save(dest/'provenance.json',dict(source=str(cache),sha256=spec['archive_sha256'],immutable_shared_archive=True))
 shutil.copy2(BASE/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
 save(R/'tasks.json',dict(benchmark='Terminal-Bench 2.0',commit=COMMIT,population=89,selection=selection['selection'],tasks=tasks))
 save(R/'dependencies/ready.json',dict(commit=COMMIT,files={p.relative_to(R/'dependencies').as_posix():sha(p) for p in (R/'dependencies').rglob('*') if p.is_file()}))
 (R/'environment-locks').mkdir();save(R/'history.json',{})
 edit('queue_policy.py',"ARMS=('hld','recuris')","ARMS=('hld-old','hld-new')")
 edit('queue_policy.py','39','10');edit('queue_policy.py','tb2hr10-','tb2hm10-')
 edit('agents.py',"arm='hld'","arm='hld-old'");edit('agents.py',"arm='recuris'","arm='hld-new'")
 edit('agents.py','hld-v7-tb2','hld-v7-frozen');edit('agents.py','recuris-v5-tb4','hld-v8-mechanism')
 edit('entry_probe.py',"'dsh' if agent.arm=='recuris' else 'kz'","'kz'")
 edit('acceptance.py',"['hld','recuris']","['hld-old','hld-new']");edit('acceptance.py',"'build-pmars'","'extract-elf'")
 edit('campaign.py',"row['arm']=='hld'","row['arm']=='hld-old'")
 edit('campaign.py',"CAMPAIGN_BUDGET_ARM='dsh' if row['arm']=='recuris' else 'kz'","CAMPAIGN_BUDGET_ARM='kz'")
 edit('campaign.py',"hld_monetary_stop(live,row['arm'],exit_valid,code)","hld_monetary_stop(live,'hld',exit_valid,code)")
 edit('campaign.py','29211','29321');edit('campaign.py','29212','29322');edit('campaign.py','total_trials=78','total_trials=20')
 edit('tb_capacity_policy.py',"['hld','recuris']","['hld-old','hld-new']")
 edit('tb_capacity_policy.py',"other='recuris' if arm=='hld' else 'hld'","other='hld-new' if arm=='hld-old' else 'hld-old'")
 edit('experiment.py','39','10');edit('experiment.py','78','20');edit('experiment.py','complement10_of_frozen10_20261021','frozen_prior_failures_hash_seed_20261022')
 for name in ['warm_dependencies.py','ensure_cache.py']:
  edit(name,'tb2hr39-', 'tb2hm10-')
 edit('warm_dependencies.py','tb2-hld-recuris39-20261021',R.name)
 from queue_policy import initial_rows
 from experiment import EXPECTED,protocol_fields
 rows=initial_rows(names,{})
 save(R/'claimed-pending.json',dict(rows=rows));save(R/'experiment.json',EXPECTED)
 profile=read(BASE/'budget-profile.json');profile.update(campaign_limit_microcny=160000000,task_limit_microcny=8000000,jobs=[r['job'] for r in rows]);save(R/'budget-profile.json',profile)
 protocol=read(BASE/'protocol.json');protocol.update(arms=['HLD v7 frozen','HLD v8 mechanism fixes'],selection=names,paired_tasks=10,historical_exposure='Selected prior scored failures. Diagnostic retest; previous solutions and private graders excluded from solver context.',**protocol_fields(EXPECTED));protocol['budget']['campaign_cny']=160
 save(R/'protocol.json',protocol)
 bundle=R/'bundle';bundle.mkdir()
 subprocess.run(['tar','-xzf',str(TB50/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz'],check=True)
 # Replace only this new bundle. Historical runtime and results remain untouched.
 for arm,folder,source in [('hld-old','hld-old','baseline'),('hld-new','kz','candidate')]:
  dest=bundle/folder;dest.mkdir(exist_ok=True)
  for sub in ['src','scripts','config']:
   target=dest/sub
   if target.exists():
    assert target.resolve().is_relative_to(bundle.resolve());shutil.rmtree(target)
   shutil.copytree(R/source/sub,target)
  if folder=='hld-old':(dest/'node_modules').symlink_to('../kz/node_modules',target_is_directory=True)
 patch=(bundle/'kz/.runtime/kz.patch.yml').read_text()
 assert 'limitCny: 8' in patch
 (bundle/'kz/.runtime/hld-old.patch.yml').write_text(patch.replace('/opt/kz/src/plugin.mjs','/opt/hld-old/src/plugin.mjs'))
 boot=bundle/'kz/boot-guard.mjs';s=boot.read_text();s=s.replace("['hld','kzdsh-new']","['hld','kzdsh-new','hld-old','hld-new']");assert "['hld','kzdsh-new','hld-old','hld-new']" in s;boot.write_text(s)
 loop=bundle/'kz/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js';s=loop.read_text()
 old='if (turnEnds === null || turnEnds.kind !== "max-tokens") turnEnds = stepEnd;'
 new='turnEnds = stepEnd; // A resumed step replaces the previous step stop reason.'
 assert s.count(old)==1
 loop.with_name(loop.name+'.before-max-tokens').write_text(s);loop.write_text(s.replace(old,new))
 shutil.copy2(H/'tb2-hld-polyglot-repair5-20261021/test_loop.mjs',R/'test_loop.mjs')
 subprocess.run([str(bundle/'node/bin/node'),str(R/'test_loop.mjs'),str(loop)],check=True)
 s=(TB50/'container-run.mjs').read_text().replace("['hld','recuris']","['hld-old','hld-new']").replace("bundle.arm==='recuris'?'dsh':'kz'","'kz'")
 old="...(bundle.arm==='hld'?['.runtime/kz.patch.yml','.runtime/hld-new-context.patch.yml']:[])"
 assert old in s
 s=s.replace(old,"...(bundle.arm==='hld-old'?['.runtime/hld-old.patch.yml']:['.runtime/kz.patch.yml']),'.runtime/hld-new-context.patch.yml'")
 start=s.index("if(bundle.arm==='recuris'){");end=s.index("args.push('--json'",start);s=s[:start]+s[end:]
 (R/'container-run.mjs').write_text(s);(bundle/'kz/container-run.mjs').write_text(s)
 save(R/'algorithm-source-lock.json',{arm:{p.relative_to(bundle).as_posix():sha(p) for p in (bundle/folder/'src').glob('*.mjs')} for arm,folder in [('hld-old','hld-old'),('hld-new','kz')]})
 for name,digest in read(R/'baseline-lock.json').items():assert sha(R/'baseline'/name.replace('\\','/'))==digest
 save(R/'common-engineering.json',dict(max_tokens_fixed_both=True,loop_sha256=sha(loop),context_patch_sha256=sha(bundle/'kz/.runtime/hld-new-context.patch.yml'),same_model_temperature_token_budget=True))
 subprocess.run(['tar','-czf',str(R/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz','hld-old'],check=True)
 save(R/'prepared.json',dict(passed=True,paid_calls=0,tasks=10,trials=20,per_run_cny=8,campaign_cny=160,runtime_sha256=sha(R/'runtime-final.tar.gz')))
 print('PREPARED: 10 paired tasks, 20 runs, 160 CNY cap, zero model calls',flush=True)
if __name__=='__main__':main()
