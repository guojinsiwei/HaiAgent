"""Isolated from-scratch budget sensitivity run. No model calls during preparation."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tarfile,tomllib
R=Path(__file__).resolve().parent
H=R.parent
B=H/'tb2-hld-recuris39-20261021'
T=H/'tb2-hld-recuris50-20261020'
SOURCE=H/'tb2-three-arm50-20261017/official-source'
COMMIT='69671fbaac6d67a7ef0dfec016cc38a64ef7a77c'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def replace(p,a,b):
 s=p.read_text();assert a in s,(p,a);p.write_text(s.replace(a,b))
def main():
 assert not (R/'prepared.json').exists() and not (R/'launch-once.marker').exists()
 s=read(R/'selection.json');rows=s['rows'];names=list(dict.fromkeys(r['task'] for r in rows))
 assert len(rows)==10 and s['budget']['campaign_cny']==160
 assert subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()==COMMIT
 assert not subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True).strip()
 files=['agents.py','host_agent.py','entry_harbor.py','entry_probe.py','trial_runner.py','lifecycle_guard.py','verifier_setup.py','submission_snapshot.py','storage.py','recovery.py','receipts.py','budget_classification.py','spending.py','ensure_cache.py','warm_dependencies.py','image_readiness.py','test_bounded_ledger.py','campaign.py','queue_policy.py','launch_private.py']
 for n in files:shutil.copy2(B/n,R/n)
 for n in ['python-runtime.tar.gz','verifier-deps.tar.gz']:os.link(B/n,R/n)
 (R/'venv').symlink_to(B/'venv',target_is_directory=True)
 tasks=[]
 for name in names:
  data=tomllib.loads((SOURCE/name/'task.toml').read_text());tasks.append(dict(name=name,**{k:data.get(k,{}) for k in ['metadata','environment','agent','verifier']}))
  shutil.copytree(SOURCE/name,R/'dependencies/official/tasks'/name)
  cache=next(p for p in [B/'dependency-cache'/name,T/'dependency-cache'/name] if (p/'ready.json').exists() and (p/'dependencies.tar').exists())
  spec=read(cache/'ready.json');assert spec['test_sha256']==sha(SOURCE/name/'tests/test.sh') and spec['archive_sha256']==sha(cache/'dependencies.tar')
  out=R/'dependency-cache'/name;out.mkdir(parents=True);os.link(cache/'dependencies.tar',out/'dependencies.tar');shutil.copy2(cache/'ready.json',out/'ready.json')
 shutil.copy2(B/'dependencies/network_proxy.py',R/'dependencies/network_proxy.py')
 save(R/'dependencies/ready.json',dict(commit=COMMIT,files={p.relative_to(R/'dependencies').as_posix():sha(p) for p in (R/'dependencies').rglob('*') if p.is_file()}))
 save(R/'tasks.json',dict(benchmark='Terminal-Bench 2.0',commit=COMMIT,tasks=tasks))
 (R/'environment-locks').mkdir();save(R/'history.json',{});save(R/'claimed-pending.json',dict(rows=rows))
 profile=read(B/'budget-profile.json');profile.update(campaign_limit_microcny=160000000,task_limit_microcny=16000000,requests_per_task=800,tools_per_task=1200,jobs=[r['job'] for r in rows]);save(R/'budget-profile.json',profile)
 protocol=read(B/'protocol.json');protocol.update(selection=names,total_trials=10,max_trials_with_retry=10,paired_tasks=None,selection_kind='Selected arm-task budget diagnostic; asymmetric subset, not whole-benchmark head-to-head',historical_exposure='Prior failed monetary-stop attempts selected offline. Only original task instruction reaches solver; no prior artifacts, hints or audit reports.',concurrency={'total':6,'per_arm_when_both_waiting':3},algorithm_policy=s['version_policy'])
 protocol['budget'].update(per_run_cny=16,campaign_cny=160,shared_requests=800,shared_tools=1200)
 protocol['experiment']=dict(schema_version=11,task_count=len(names),trial_count=10,concurrency=6,solver_seconds=7200,engineering_retry_batches=0)
 save(R/'protocol.json',protocol);save(R/'experiment.json',protocol['experiment'])
 # Same source algorithms as both original campaigns. Modify only budget config and common runtime fix.
 bundle=R/'bundle';bundle.mkdir()
 subprocess.run(['tar','-xzf',str(B/'runtime-final.tar.gz'),'-C',str(bundle)],check=True)
 baseline={p.relative_to(bundle).as_posix():sha(p) for prefix in ['kz/src','recuris-dsh','dsh-baselines'] for p in (bundle/prefix).rglob('*') if p.is_file() and 'node_modules' not in p.parts}
 with tarfile.open(T/'runtime-final.tar.gz') as tf:
  for n,digest in baseline.items():assert hashlib.sha256(tf.extractfile(n).read()).hexdigest()==digest,n
 save(R/'algorithm-source-lock.json',baseline)
 replace(bundle/'kz/.runtime/kz.patch.yml','limitCny: 8','limitCny: 16')
 replace(bundle/'kz/.runtime/kz.patch.yml','maxRequests: 400','maxRequests: 800')
 replace(bundle/'kz/.runtime/kz.patch.yml','maxTools: 600','maxTools: 1200')
 for a,b in [('state.requests>=400','state.requests>=800'),('state.tools>=600','state.tools>=1200'),('requests:400,tools:600,seconds:3000,estimatePeakCny:8','requests:800,tools:1200,seconds:7200,estimatePeakCny:16')]:replace(bundle/'kz/shared-budget.mjs',a,b)
 loop=bundle/'kz/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js';code=loop.read_text();old='if (turnEnds === null || turnEnds.kind !== "max-tokens") turnEnds = stepEnd;'
 if old in code:
  loop.with_name(loop.name+'.before-max-tokens').write_text(code)
  loop.write_text(code.replace(old,'turnEnds = stepEnd; // Resumed step replaces previous stop reason.'))
 shutil.copy2(H/'tb2-hld-polyglot-repair5-20261021/test_loop.mjs',R/'test_loop.mjs')
 finish()
def finish():
 bundle=R/'bundle';baseline=read(R/'algorithm-source-lock.json');names=[x['name'] for x in read(R/'tasks.json')['tasks']]
 loop=bundle/'kz/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js'
 if not loop.with_name(loop.name+'.before-max-tokens').exists():
  with tarfile.open(B/'runtime-final.tar.gz') as tf:loop.with_name(loop.name+'.before-max-tokens').write_bytes(tf.extractfile(loop.relative_to(bundle).as_posix()).read())
 subprocess.run([str(bundle/'node/bin/node'),str(R/'test_loop.mjs'),str(loop)],check=True)
 runner=(B/'container-run.mjs').read_text().replace('apiRequests:400,tools:600','apiRequests:800,tools:1200')
 assert 'apiRequests:800,tools:1200' in runner
 (R/'container-run.mjs').write_text(runner);(bundle/'kz/container-run.mjs').write_text(runner)
 for n,digest in baseline.items():assert sha(bundle/n)==digest
 subprocess.run(['tar','-czf',str(R/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz','recuris-dsh','dsh-baselines'],check=True)
 # Keep established infrastructure; isolate queue, ports, budget ledger and result paths.
 replace(R/'campaign.py','29211','29411');replace(R/'campaign.py','29212','29412')
 replace(R/'campaign.py','if len(active)>=8:break','if len(active)>=6:break')
 replace(R/'campaign.py','total_trials=78','total_trials=10');replace(R/'campaign.py','total_concurrency=8','total_concurrency=6')
 for n in ['ensure_cache.py','warm_dependencies.py']:replace(R/n,'tb2hr39-','tb2bd10-')
 q=(R/'queue_policy.py').read_text();start=q.index('def initial_rows');end=q.index('def first_finished',start)
 q=q[:start]+'''def initial_rows(names,history):
 import json
 from pathlib import Path
 return json.loads((Path(__file__).resolve().parent/'selection.json').read_text())['rows']
'''+q[end:];(R/'queue_policy.py').write_text(q)
 save(R/'prepared.json',dict(passed=True,paid_calls=0,trials=10,task_count=len(names),budget_cny=160,per_run_cny=16,requests=800,tools=1200,runtime_sha256=sha(R/'runtime-final.tar.gz')))
 print('PREPARED 10 runs, 160 CNY, no paid calls',flush=True)
if __name__=='__main__':
 import sys
 if '--finish' in sys.argv:finish()
 else:main()
