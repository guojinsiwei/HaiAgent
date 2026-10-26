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
    for name in ['common.py','model-config.json','experiment.json','environment.py','worker.py','task-manifest.json','grading_cache.py','cache_assets.py','jobs.json','desktop_ready.py','launch.py']:
        h.update(name.encode());h.update((ROOT/name).read_bytes())
    return h.hexdigest()

def verify_ready():
    agent=json.loads((ROOT/'preflight-multistep/passed.json').read_text())
    setup=json.loads((ROOT/'environment-preflight.json').read_text())
    assert len(agent['arms'])==2 and all(r['passed'] and r['cpu_only'] and r['source_sha256']==source_hash() for r in agent['arms'])
    assert setup['passed'] and setup['deployment_sha256']==deployment_hash()
    assert setup['multistep_deployment_sha256']==agent['deployment_sha256']
    assert setup['model_config_sha256']==hashlib.sha256((ROOT/'model-config.json').read_bytes()).hexdigest()
    return agent
def config(task,mode,bucket=None):
    base=json.loads((ROOT/'model-config.json').read_text())
    return {**base,'task_id':task,'mode':mode,'budget_cny':8,'source_sha256':source_hash(),
      'deployment_sha256':deployment_hash(),'shared_budget':{'path':str(ROOT.parent/'budget.sqlite'),
      'bucket':bucket or mode+'/'+task,'total_limit_cny':480,'bucket_limit_cny':8}}
