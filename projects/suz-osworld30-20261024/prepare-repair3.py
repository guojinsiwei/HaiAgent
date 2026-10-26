"""Prepare an isolated repair deployment; never overwrite the original round."""
from pathlib import Path
import json,shutil
ROOT=Path(__file__).resolve().parent
DEST=ROOT/'repair3'
DEST.mkdir(exist_ok=True)
for name in ['AGENTS.md','common.py','environment.py','cache_assets.py','model-config.json','experiment.json',
             'worker.py','launch.py','task-manifest.json','assets-preflight.json','preflight-multistep.py','status.py']:
    shutil.copy2(ROOT/name,DEST/name)

p=DEST/'common.py';s=p.read_text();s=s.replace("ROOT/'budget.sqlite'","ROOT.parent/'budget.sqlite'")
s=s.replace("'worker.py','task-manifest.json'","'worker.py','task-manifest.json','grading_cache.py','cache_assets.py','repair-jobs.json'")
p.write_text(s)
p=DEST/'model-config.json';cfg=json.loads(p.read_text());cfg.update(bounded_response_recovery=True,semantic_completion_audit=True);p.write_text(json.dumps(cfg,indent=2))
p=DEST/'environment.py';s=p.read_text().replace('def make_environment():','def make_environment(cache_dir):')
s=s.replace("ROOT/'cpu-vm-start.lock'","ROOT.parent/'cpu-vm-start.lock'")
s=s.replace("cache_dir=str(ROOT/'assets')","cache_dir=str(cache_dir)");p.write_text(s)
p=DEST/'worker.py';s=p.read_text().replace('from cache_assets import prefetch','from grading_cache import prepare_cache, archive_cache')
s=s.replace("prefetch(task);env=make_environment();obs=env.reset(task_config=task)","initial_cache=prepare_cache(ROOT/'assets',directory/'preflight-cache',task['id']);env=make_environment(initial_cache);obs=env.reset(task_config=task)")
s=s.replace("env=make_environment();agent=SUZAgent", "eval_cache=prepare_cache(ROOT/'assets',directory/'evaluation-cache',task['id']);env=make_environment(eval_cache);agent=SUZAgent")
s=s.replace("status.update(stage='completed',outcome=outcome)","status.update(stage='completed',outcome=outcome);archive_cache(eval_cache,directory/'grading-artifacts.json')")
p.write_text(s)
p=DEST/'preflight-multistep.py';s=p.read_text().replace('env=make_environment()',"env=make_environment(directory/'evaluation-cache')")
s=s.replace("common.config('multistep-v2',mode,'preflight-multistep')","common.config('multistep-repair3',mode,'preflight-repair3')")
s=s.replace("assert state['contractReady'] and state['review']['accepted']","assert state['contractReady'] and state['review']['accepted']\n            assert state['completionAudit']['decision']=='supported'")
p.write_text(s)

rows=json.loads((ROOT/'task-manifest.json').read_text())['tasks'];jobs=[]
semantic={'2cd43775-7085-45d8-89fa-9e35c0a915cf','5ac2891a-eacd-4954-b339-98abba077adb'}
for i,row in enumerate(rows):
    for mode in ['opencua_baseline','suz']:
        result=json.loads((ROOT/'audit-repair3/runs'/mode/row['id']/'result.json').read_text())
        reason='engineering_stop' if result['official_score']!=1 and result['outcome_kind']=='engineering_failure' else None
        if mode=='suz' and row['id'] in semantic:reason='confirmed_semantic_completion_error'
        if reason:jobs.append({'index':i,'mode':mode,'id':row['id'],'reason':reason,'original_score':result['official_score']})
(DEST/'repair-jobs.json').write_text(json.dumps(jobs,indent=2))
p=DEST/'launch.py';s=p.read_text();start=s.index('jobs=[(');end=s.index('\n',start)
s=s[:start]+"jobs=[(r['index'],r['mode']) for r in json.loads((ROOT/'repair-jobs.json').read_text())]"+s[end:]
p.write_text(s)
print(json.dumps({'repair_jobs':len(jobs),'by_mode':{m:sum(r['mode']==m for r in jobs) for m in ['opencua_baseline','suz']}}))
