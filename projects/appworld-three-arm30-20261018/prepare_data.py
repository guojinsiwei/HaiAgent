"""Run only in the trusted preparation container, with no model credentials."""
from pathlib import Path
import hashlib,json,random,shutil
from appworld import load_task_ids
R=Path('/control');data=Path('/appworld/data')
ids=load_task_ids('test_normal')
groups={}
for task in ids:groups.setdefault(task.rsplit('_',1)[0],[]).append(task)
assert len(ids)==168 and all(len(g)==3 for g in groups.values())
selected=random.Random(20261018).sample(sorted(groups),10)
tasks=[task for scenario in selected for task in sorted(groups[scenario])]
public=R/'public-data';public.mkdir(exist_ok=True)
for part in ['api_docs','base_dbs']:
    if not (public/part).exists():shutil.copytree(data/part,public/part)
shutil.copy2(data/'version.txt',public/'version.txt')
rows=[]
for task in tasks:
    dst=public/'tasks'/task;dst.mkdir(parents=True,exist_ok=True)
    shutil.copy2(data/'tasks'/task/'specs.json',dst/'specs.json')
    if not (dst/'dbs').exists():shutil.copytree(data/'tasks'/task/'dbs',dst/'dbs')
    specs=json.loads((dst/'specs.json').read_text())
    rows.append({'task':task,'scenario':task.rsplit('_',1)[0],'instruction':specs['instruction'],
                 'supervisor':specs.get('supervisor',specs.get('main_user')),'datetime':specs['datetime']})
assert not list(public.rglob('ground_truth'))
manifest={str(p.relative_to(public)):hashlib.sha256(p.read_bytes()).hexdigest() for p in public.rglob('*') if p.is_file()}
(R/'task-manifest.json').write_text(json.dumps({'seed':20261018,'split':'test_normal','scenarios':selected,'tasks':rows,'public_data_hashes':manifest},indent=2))
print(json.dumps({'tasks':len(tasks),'scenarios':len(selected),'ground_truth_excluded':True,'public_files':len(manifest)}))
