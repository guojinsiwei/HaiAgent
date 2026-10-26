import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'SUZ'
def source_hash():
    h=hashlib.sha256()
    for p in sorted(SOURCE.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(p.relative_to(SOURCE).as_posix().encode());h.update(p.read_bytes())
    return h.hexdigest()
def deployment_hash():
    h=hashlib.sha256(source_hash().encode())
    for name in ['common.py','model-config.json','experiment.json','environment.py','worker.py','task-manifest.json']:
        h.update(name.encode());h.update((ROOT/name).read_bytes())
    return h.hexdigest()
def config(task,mode,bucket=None):
    base=json.loads((ROOT/'model-config.json').read_text())
    return {**base,'task_id':task,'mode':mode,'budget_cny':8,'source_sha256':source_hash(),
      'deployment_sha256':deployment_hash(),'shared_budget':{'path':str(ROOT/'budget.sqlite'),
      'bucket':bucket or mode+'/'+task,'total_limit_cny':480,'bucket_limit_cny':8}}
