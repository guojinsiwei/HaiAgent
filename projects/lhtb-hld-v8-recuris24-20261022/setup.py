"""Freeze LHTB and v8/Recuris sources; zero paid calls."""
from pathlib import Path
import ast,hashlib,json,os,shutil,subprocess,sys
R=Path(__file__).resolve().parent;B=R.parent
OLD=B/'tb2-hld-recuris50-20261020';V8=B/'tb2-hld-mechanism-ab10-20261022';LONG=B/'longcli-hld-full20-triple-20261022'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def once(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)

assert not (R/'prepared.json').exists()
selection=read(R/'selection.json');assert len(selection['tasks'])==24 and selection['budget']['campaign_cny']==1152
for n in ['host_agent.py','spending.py']:shutil.copy2(V8/n,R/n)
os.link(V8/'python-runtime.tar.gz',R/'python-runtime.tar.gz')
(R/'venv').symlink_to(V8/'venv',target_is_directory=True)
shutil.copytree(R/'upstream/harbor/src',R/'vendor-src')
trial=R/'vendor-src/harbor/trial/trial.py';s=trial.read_text()
# A monetary/request/tool/provider stop is a terminal resource condition, never a new paid phase.
s=once(s,'                reason = phase_context.metadata.get("termination_reason")','                reason = phase_context.metadata.get("termination_reason")\n                if reason in {"per_task_budget_exhausted", "campaign_budget_exhausted", "per_task_request_limit", "per_task_tool_limit", "provider_stop", "solver_wall_limit", "usage_unavailable"}:\n                    break')
# Docker bind mounts must retain host evidence, while the agent sees an empty verifier directory.
old='''        try:
            await self._environment.reset_dirs(
                remove_dirs=remove_dirs,
                create_dirs=create_dirs,
            )'''
new='''        try:
            if provider == "docker":
                live = self._trial_paths.verifier_dir
                if live.exists() and any(live.iterdir()):
                    phase_root = self.trial_dir / "operator-verifier-phases"
                    phase_root.mkdir(exist_ok=True)
                    snapshot = phase_root / f"phase-{len(list(phase_root.iterdir())):04d}"
                    _relocate_dir_contents(live, snapshot)
                await self._environment.exec("find /tmp -maxdepth 1 -type d -name 'pytest-of-*' -exec rm -rf -- {} +", timeout_sec=30)
            await self._environment.reset_dirs(
                remove_dirs=remove_dirs,
                create_dirs=create_dirs,
            )'''
assert old in s;s=s.replace(old,new,1);trial.write_text(s)
compile(s,str(trial),'exec')
bundle=R/'bundle';bundle.mkdir()
subprocess.run(['tar','-xzf',str(OLD/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz','recuris-dsh','dsh-baselines'],check=True)
for n in ['src','config','scripts']:
 target=bundle/'kz'/n;assert target.resolve().is_relative_to(bundle.resolve());shutil.rmtree(target);shutil.copytree(V8/'bundle/kz'/n,target)
# The same repaired DSH substrate is used for both algorithms.
loop=bundle/'kz/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js'
source=V8/'bundle/kz/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js';shutil.copy2(source,loop)
for n in ['kz.patch.yml','hld-new-context.patch.yml','transport.patch.yml']:
 shutil.copy2(V8/'bundle/kz/.runtime'/n,bundle/'kz/.runtime'/n)
patch=bundle/'kz/.runtime/kz.patch.yml';s=patch.read_text();assert 'efficiencyEnabled: true' not in s
s=s.replace('maxRequests: 400','maxRequests: 800').replace('limitCny: 8','limitCny: 24').replace('maxOutputTokens: 16384','maxOutputTokens: 32768').replace('wallSeconds: 7200','wallSeconds: 10800');patch.write_text(s)
context=bundle/'kz/.runtime/hld-new-context.patch.yml';s=context.read_text().replace('headroomTokens: 16384','headroomTokens: 32768');context.write_text(s)
route=bundle/'kz/route.patch.yml';s=route.read_text().replace('maxTokens: 16384','maxTokens: 32768');route.write_text(s)
shared=(LONG/'runtime/kz/shared-budget-high.mjs').read_text()
shared=once(shared,"import {appendFileSync,writeFileSync,renameSync} from 'node:fs';","import {appendFileSync,writeFileSync,renameSync,readFileSync,existsSync} from 'node:fs';")
shared=once(shared,"  const dir=process.env.PAIRED_AUDIT_DIR;","  const dir=process.env.PAIRED_AUDIT_DIR;\n  if(existsSync(dir+'/shared-state.json'))Object.assign(state,JSON.parse(readFileSync(dir+'/shared-state.json','utf8')));")
(bundle/'kz/shared-budget.mjs').write_text(shared)
entry=(OLD/'container-run.mjs').read_text().replace("['hld','recuris']","['hld-new','recuris']")
entry=once(entry,"const cwd=process.cwd();if(cwd==='/')throw Error('Explicit task workspace required');","const cwd=process.cwd();if(cwd==='/')throw Error('Explicit task workspace required');\nconst phaseDir='/logs/agent/phase-'+String(bundle.phase).padStart(4,'0');fs.mkdirSync(phaseDir,{recursive:true});")
entry=once(entry,"{flag:'wx'}","{flag:'w'}")
entry=entry.replace("KZ_AUDIT_DIR:logs+'/kz'","KZ_AUDIT_DIR:phaseDir+'/kz'")
entry=entry.replace("DSH_HOME:logs+'/dsh-home'","DSH_HOME:phaseDir+'/dsh-home'")
entry=entry.replace("KZ_AUDIT_DIR:phaseDir+'/kz'","KZ_AUDIT_DIR:phaseDir+'/kz',RECURIS_AUDIT_DIR:phaseDir+'/recuris'")
entry=entry.replace("bundle.arm==='hld'?","bundle.arm==='hld-new'?")
entry=entry.replace('maxTokens:16384','maxTokens:32768').replace('apiRequests:400','apiRequests:800').replace('wallSeconds:7200','wallSeconds:bundle.remaining_seconds')
entry=entry.replace("auditDir:logs+'/recuris'","auditDir:phaseDir+'/recuris'")
entry=entry.replace("const patch=logs+'/recuris.patch.yml'","const patch=phaseDir+'/recuris.patch.yml'")
entry=entry.replace("fs.openSync(logs+'/dsh.jsonl','wx')","fs.openSync(phaseDir+'/dsh.jsonl','wx')").replace("fs.openSync(logs+'/dsh.stderr.log','wx')","fs.openSync(phaseDir+'/dsh.stderr.log','wx')")
entry=entry.replace('deadline(child,7200,','deadline(child,bundle.remaining_seconds,')
entry=entry.replace("logs+'/agent-exit.json'","phaseDir+'/agent-exit.json'")
(bundle/'kz/container-run.mjs').write_text(entry)
boot=bundle/'kz/boot-guard.mjs';s=boot.read_text().replace("['hld','kzdsh-new']","['hld','kzdsh-new','hld-new']");boot.write_text(s)
s=boot.read_text().replace("path.join(audit,'recuris/state.json')","path.join(process.env.RECURIS_AUDIT_DIR??path.join(audit,'recuris'),'state.json')");boot.write_text(s)
subprocess.run([str(bundle/'node/bin/node'),'--check',str(bundle/'kz/container-run.mjs')],check=True)
subprocess.run(['tar','-czf',str(R/'runtime-final.tar.gz'),'-C',str(bundle),'node','kz','recuris-dsh','dsh-baselines'],check=True)
rows=[dict(task=t['name'],arm=a,job=f'lhtb24-{i+1:02d}-{a}-{t["name"]}',state='pending') for i,t in enumerate(selection['tasks']) for a in (['hld','recuris'] if i%2==0 else ['recuris','hld'])]
profile=read(V8/'budget-profile.json');profile.update(campaign_limit_microcny=1152000000,task_limit_microcny=24000000,max_output_tokens=32768,requests_per_task=800,solver_seconds=10800,jobs=[r['job'] for r in rows]);save(R/'budget-profile.json',profile)
protocol=dict(benchmark='LHTB original46 CLI subset',commit=selection['commit'],task_count=24,total_trials=48,arms=['HLD v8','Recuris'],model='deepseek-flash',temperature=0,thinking=False,context_tokens=128000,max_output_tokens=32768,requests_per_task=800,tools_per_task=600,solver_seconds=10800,task_budget_cny=24,campaign_budget_cny=1152,all_auxiliary_calls_included=True,concurrency=6,per_arm_concurrency=3,continue_until_timeout=True,verifier_feedback='binary only',cross_task_memory=False,automatic_paid_retries=False,selection=selection,engineering_overlay=['stop on bounded resources without restarting budget','archive intermediate Docker verifier logs outside agent mounts and clear grader temp fixtures'],v8_source=str(V8/'bundle/kz/src'),recuris_source=str(OLD/'bundle/recuris-dsh/src'))
save(R/'protocol.json',protocol);save(R/'queue.json',dict(rows=rows))
save(R/'algorithm-source-lock.json',{arm:{str(p.relative_to(bundle)):sha(p) for p in (bundle/folder/'src').rglob('*') if p.is_file()} for arm,folder in [('HLD v8','kz'),('Recuris','recuris-dsh')]})
save(R/'prepared.json',dict(passed=True,model_calls=0,runtime_sha256=sha(R/'runtime-final.tar.gz'),official_harbor_commit=selection['commit'],overlay_trial_sha256=sha(trial)))
print(json.dumps(dict(prepared=True,tasks=24,trials=48,model_calls=0)))
