"""Package public-only fleet workers; original solver and budgets remain sealed."""
import json,tarfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ORIGINAL='/var/tmp/longcli-dh-tools-execution-repair3-20261008'
def main():
 p=json.loads((ROOT/'protocol.json').read_text())
 handoff=json.loads((ROOT/'fleet-handoff.json').read_text())
 rows={r['task']:r for r in p['tasks']};pending=[rows[t] for t in handoff['pending_tasks']]
 assert len(pending)==10,'Recompute allocation for a different remaining task count'
 plan={'source_campaign':ORIGINAL,'time':time.time(),'target_concurrency':12,
       'assignments':{'college':pending[:6],'cube0':pending[6:8],'cube1':pending[8:]},
       'node_limits':{'college':8,'cube0':2,'cube1':2},
       'model_budget_changed':False,'algorithm_changed':False,'mail_enabled':False,
       'execution_environment_difference':'Cube has private rootfs namespaces and shared 16GB container; not independent Docker 8GiB cgroup'}
 (ROOT/'fleet-plan.json').write_text(json.dumps(plan,indent=2))
 (ROOT/'resume-plan.json').write_text(json.dumps({'source':ORIGINAL,'time':plan['time'],'preserved':[]}))
 (ROOT/'notifications-disabled.json').write_text(json.dumps({'enabled':False,'reason':'user_disabled'}))
 allowed={'.py','.json','.txt','.toml','.ps1','.md','.yaml','.yml'}
 with tarfile.open(ROOT/'fleet-deployment.tar.gz','w:gz') as tar:
  for f in ROOT.rglob('*'):
   if not f.is_file() or f.suffix not in allowed:continue
   rel=f.relative_to(ROOT)
   if any(x in {'__pycache__','.pytest_cache','.git','received','public'} for x in rel.parts):continue
   if len(rel.parts)>1 and rel.parts[0] not in ('sources','compatibility','tests','evidence'):continue
   tar.add(f,arcname=rel.as_posix())
 print(json.dumps({'assignments':{k:[r['task'] for r in v] for k,v in plan['assignments'].items()},'mail_enabled':False}))
if __name__=='__main__':main()
