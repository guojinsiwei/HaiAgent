"""Extend the frozen SHA256 ranking from two to three tasks per domain."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'suz-osworld20-20261023'
meta=json.loads((ROOT/'OSWorld/evaluation_examples/test_all.json').read_text())
seed='SUZ-OSWorld-20261023-20';rows=[]
for domain,ids in sorted(meta.items()):
    ranked=sorted(ids,key=lambda x:hashlib.sha256(f'{seed}/{domain}/{x}'.encode()).hexdigest())
    for task_id in ranked[:3]:
        src=ROOT/'OSWorld/evaluation_examples/examples'/domain/(task_id+'.json')
        dst=ROOT/'tasks'/domain/src.name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dst);task=json.loads(src.read_text())
        rows.append({'id':task_id,'domain':domain,'path':dst.relative_to(ROOT).as_posix(),
          'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'instruction':task['instruction']})
assert len(rows)==30 and len(set(r['id'] for r in rows))==30
old=json.loads((OLD/'task-manifest.json').read_text())
assert set(r['id'] for r in old['tasks']).issubset(set(r['id'] for r in rows))
manifest={'commit':old['commit'],'seed':seed,'selection':'Three tasks per domain using unchanged SHA256 ranking; extends original20 without result filtering. Both arms run all30 fresh.','tasks':rows}
(ROOT/'task-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
base=json.loads((OLD/'model-config.json').read_text())
base.update(coordinate_type='absolute',max_output_tokens=32768,initial_output_tokens=16384,
            role_max_tokens=16384,truncation_recovery_tokens=32768,request_timeout=480)
(ROOT/'model-config.json').write_text(json.dumps(base,indent=2))
(ROOT/'experiment.json').write_text(json.dumps({'name':ROOT.name,'total_cny':480,'task_cny':8,'tasks':30,
    'runs':60,'max_concurrency':2,'max_steps':100,'max_requests':400,'max_seconds':7200,
    'gpu_allowed':False,'fresh_comparison':True,'model':'glm-5.3-flash'},indent=2))
print(json.dumps({'tasks':len(rows),'retained_original_tasks':20,'new_tasks':10,'model_calls':0}))
