"""Versioned TB4 pair: no model calls; preserve old campaigns and official tasks."""
from pathlib import Path
import shutil,json,tarfile,hashlib,subprocess,os
R=Path(__file__).resolve().parent
HOME=R.parent
TB=HOME/'tb2-three-arm50-20261017'
OLD=HOME/'tb4-kz-ec3-bounded10-20261016'
V5=HOME/'appworld-three-arm30-20261018/repair-v5'
NAMES=['payments-pipeline-fix','fin-saccr-rwa','mvcc-lsm-compaction','uefi-bootkit','retro-console-soc','gsea-proteomics','coq-block-bound']
def save(name,value):(R/name).write_text(json.dumps(value,indent=2))
def change(file,old,new):
 p=R/file;s=p.read_text();assert old in s,(file,old[:60]);p.write_text(s.replace(old,new))
def main():
 assert not (R/'prepared.json').exists()
 for name in ['campaign.py','host_agent.py','trial_runner.py','storage.py','recovery.py','receipts.py','lifecycle_guard.py','entry_harbor.py','spending.py','test_bounded_ledger.py']:
  shutil.copy2(TB/name,R/name)
 deps=R/'dependencies';deps.mkdir(exist_ok=True)
 shutil.copy2(OLD/'dependencies/network_proxy.py',deps/'network_proxy.py')
 manifest=json.loads((OLD/'tasks.json').read_text());tasks=[t for t in manifest['tasks'] if t['name'] in NAMES]
 assert [t['name'] for t in tasks]==NAMES
 for name in NAMES:shutil.copytree(OLD/'dependencies/official/tasks'/name,deps/'official/tasks'/name)
 files={str(p.relative_to(deps)):hashlib.sha256(p.read_bytes()).hexdigest() for p in deps.rglob('*') if p.is_file()}
 save('dependencies/ready.json',{'files':files,'commit':manifest['commit']})
 save('tasks.json',{'benchmark':'TerminalBench 4.0.0','commit':manifest['commit'],'tasks':tasks,'selection':'First 7 text-capable tasks from previously frozen ten; exclude two image layout tasks before this run. No result-based replacement.'})
 (R/'venv').symlink_to(OLD/'venv',target_is_directory=True)
 (R/'environment-locks').mkdir()
 os.link(TB/'python-runtime.tar.gz',R/'python-runtime.tar.gz')
 runtime=R/'runtime';runtime.mkdir()
 with tarfile.open(TB/'runtime-final.tar.gz') as tar:tar.extractall(runtime,filter='data')
 # Same host/dependencies, replace algorithm/config source only.
 for name in ['src','scripts','config']:
  shutil.copytree(V5/'runtime/hld'/name,runtime/'kz'/name,dirs_exist_ok=True)
 for name in ['shared-budget.mjs','route.patch.yml','route-audit.mjs','boot-guard.mjs','provider-guard.mjs','spending-client.mjs','messages-protocol.mjs','deadline.mjs']:
  shutil.copy2(V5/'runtime/hld'/name,runtime/'kz'/name)
 for name in ['kz.patch.yml','transport.patch.yml']:
  shutil.copy2(V5/'runtime/hld/.runtime'/name,runtime/'kz/.runtime'/name)
 for arm in ['recuris-dsh','dsh-baselines']:
  shutil.copytree(V5/'runtime'/arm,runtime/arm,ignore=shutil.ignore_patterns('node_modules','.runtime','__pycache__'))
  (runtime/arm/'node_modules').symlink_to('../kz/node_modules',target_is_directory=True)
 shutil.copy2(R/'container-run.mjs',runtime/'kz/container-run.mjs')
 change('runtime/kz/boot-guard.mjs',"s.full?.taskInstruction?.path==='INSTRUCTION.md'","s.full?.taskInstruction?.path===process.env.KZ_TASK_INSTRUCTION_PATH")
 # Carry v5's planner repair across benchmarks without enabling AppWorld APIs.
 for name in ['semantic-planner.mjs','full-integration.mjs']:
  p=runtime/'kz/src'/name;s=p.read_text()
  if name=='semantic-planner.mjs':
   s=s.replace("if(process.env.KZ_APPWORLD==='1')answer=normalizePlan", "if(process.env.KZ_APPWORLD==='1'||process.env.HLD_PLANNER_PROTOCOL==='2')answer=normalizePlan")
   s=s.replace("const periodicRetention=process.env.KZ_APPWORLD==='1' && old", "const periodicRetention=(process.env.KZ_APPWORLD==='1'||process.env.HLD_PLANNER_PROTOCOL==='2') && old")
  else:s=s.replace("(process.env.KZ_APPWORLD==='1'?SEMANTIC_V2:SEMANTIC_PLANNER)","(process.env.KZ_APPWORLD==='1'||process.env.HLD_PLANNER_PROTOCOL==='2'?SEMANTIC_V2:SEMANTIC_PLANNER)")
  p.write_text(s)
 p=runtime/'kz/.runtime/kz.patch.yml';p.write_text(p.read_text().replace('limitCny: 8','limitCny: 6'))
 p=runtime/'kz/shared-budget.mjs';p.write_text(p.read_text().replace('estimatePeakCny:8','estimatePeakCny:6'))
 shutil.copy2(HOME/'tb2-three-arm50-scorefix-20261018/submission_snapshot.py',R/'submission_snapshot.py')
 change('lifecycle_guard.py',"            record(self,'artifacts_collected')","            from submission_snapshot import snapshot\n            await snapshot(self)\n            record(self,'artifacts_collected')")
 change('host_agent.py',"self.cwd=cwd", "self.cwd=cwd\n        await env.upload_file(ROOT/'python-runtime.tar.gz','/installed-agent/python-runtime.tar.gz')\n        result=await self.exec_as_root(env,'mkdir -p /opt/kz-python && tar -xzf /installed-agent/python-runtime.tar.gz --strip-components=1 -C /opt/kz-python',timeout_sec=180)\n        if result.return_code:raise RuntimeError('Portable Python installation failed')")
 change('host_agent.py',"dict(spending=", "dict(spending=") # Assert stable payload location.
 change('entry_harbor.py',"'agents:Native','agents:OfflineNative','agents:DSH','agents:PureDSH','agents:OfflineDSH','agents:OfflinePureDSH','agents:OfflineTimeout'", "'agents:HLD','agents:Recuris','agents:OfflineHLD','agents:OfflineRecuris'")
 change('campaign.py','PORT=28705','PORT=28931')
 change('campaign.py','port=28706','port=28932')
 change('campaign.py','if len(active)>=6:break','if len(active)>=4:break')
 a=(R/'campaign.py').read_text();start=a.index("    agent=('OfflinePureDSH'");end=a.index('    return [PY',start)
 a=a[:start]+"    agent=('Offline' if offline else '')+('HLD' if row['arm']=='hld' else 'Recuris')\n"+a[end:]
 a=a.replace("row['arm']=='dsh'","row['arm']=='recuris'")
 a=a.replace("wall.get('limit_seconds')==2700","wall.get('limit_seconds')==7200")
 a=a.replace('total_trials=150','total_trials=14').replace('total_concurrency=6','total_concurrency=4')
 (R/'campaign.py').write_text(a)
 # Fresh campaign only: never reconcile other controllers' reservations.
 change('spending.py','        self.ledger.reconcile_restart()','        # Isolated fresh ledger; no implicit reservation release/reclassification.')
 save('history.json',{})
 from queue_policy import initial_rows
 profile=json.loads((TB/'budget-profile.json').read_text());profile.update(campaign_limit_microcny=84000000,task_limit_microcny=6000000,requests_per_task=400,tools_per_task=600,solver_seconds=7200,jobs=[r['job'] for r in initial_rows(NAMES,{})])
 save('budget-profile.json',profile)
 from experiment import EXPECTED,protocol_fields
 save('experiment.json',EXPECTED)
 protocol={'benchmark':'TerminalBench 4.0.0','commit':manifest['commit'],'arms':['HLD v5 semantic replanning','Recuris v5 interface/stop-state repair'],'paired_tasks':7,'selection':NAMES,'model':'deepseek-flash','endpoint':profile['endpoint'],'temperature':0,'thinking':False,'budget':{'server_solver_seconds':7200,'per_run_cny':6,'campaign_cny':84,'shared_requests':400,'shared_tools':600},'fresh_container':True,'cross_task_memory':False,'original_official_verifier':True,'submission_snapshot_before_verifier':True,'v5_source':str(V5),'concurrency_note':'4 total, 2 per arm, admission pauses under low storage'}
 protocol.update(protocol_fields(EXPECTED));save('protocol.json',protocol)
 subprocess.run(['tar','-czf',str(R/'runtime-final.tar.gz'),'-C',str(runtime),'node','kz','recuris-dsh','dsh-baselines'],check=True)
 save('prepared.json',{'passed':True,'paid_calls':0,'jobs':14,'budget':84})
 print('PREPARED',flush=True)
if __name__=='__main__':main()
