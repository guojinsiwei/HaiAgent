"""Freeze a balanced pilot before seeing any agent outcomes; no model calls."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'OSWorld/evaluation_examples'
meta=json.loads((SOURCE/'test_all.json').read_text())
seed='SUZ-OSWorld-20261023-20'
rows=[]
for domain, ids in sorted(meta.items()):
    ranked=sorted(ids,key=lambda task:hashlib.sha256(f'{seed}/{domain}/{task}'.encode()).hexdigest())
    for task_id in ranked[:2]:
        source=SOURCE/'examples'/domain/(task_id+'.json')
        target=ROOT/'tasks'/domain/source.name
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.read_bytes()!=source.read_bytes():
            raise RuntimeError('Frozen task differs from upstream')
        shutil.copyfile(source,target)
        task=json.loads(source.read_text())
        rows.append({'id':task_id,'domain':domain,'path':str(target.relative_to(ROOT)),
                     'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                     'instruction':task['instruction'],'related_apps':task.get('related_apps',[])})
assert len(rows)==20 and len({r['id'] for r in rows})==20
manifest={'commit':'04718eab9327856efe8192cc58161acc7a7627e2','seed':seed,
          'selection':'Two tasks per official domain, SHA256-ranked before model runs. Balanced pilot, not the full-dataset distribution.',
          'tasks':rows}
(ROOT/'task-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'tasks':len(rows),'domains':len(meta),'model_calls':0}))
