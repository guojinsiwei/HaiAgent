"""Validate the final setup-only change with a fresh CPU VM, without model calls."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
from common import ROOT,source_hash,deployment_hash,verify_ready
from environment import make_environment
from grading_cache import prepare_cache,archive_cache
ready=json.loads((ROOT/'preflight-multistep/passed.json').read_text())
assert ready['source_sha256']==source_hash()
assert all(x['passed'] and x['cpu_only'] for x in ready['arms'])
with tarfile.open(Path('/data/share/lizh639/suz-osworld30-20261024/repair3-final.tar.gz')) as archive:
    original=archive.extractfile('model-config.json').read()
assert original==(ROOT/'model-config.json').read_bytes(),'model configuration changed since actual multistep test'
directory=ROOT/'preflight-environment';directory.mkdir(exist_ok=False)
task_id='2cd43775-7085-45d8-89fa-9e35c0a915cf'
row=next(x for x in json.loads((ROOT/'task-manifest.json').read_text())['tasks'] if x['id']==task_id)
task=json.loads((ROOT/row['path']).read_text())
cache=prepare_cache(ROOT/'assets',directory/'cache',task_id);env=None
try:
    env=make_environment(cache);obs=env.reset(task_config=task)
    host=env.provider.container.attrs['HostConfig']
    assert host['Runtime']=='runc' and not host.get('DeviceRequests')
    assert all('nvidia' not in str(x).lower() and '/dev/dri' not in str(x).lower() for x in host.get('Devices',[]))
    (directory/'initial-ready.png').write_bytes(obs['screenshot'])
    score=env.evaluate();assert isinstance(score,(int,float)) and 0<=score<=1
    archive_cache(cache,directory/'grading-artifacts.json')
    result={'passed':True,'cpu_only':True,'model_calls':0,'initial_score':score,
        'desktop_ready':json.loads((cache/'desktop-ready.json').read_text()),
        'source_sha256':source_hash(),'deployment_sha256':deployment_hash(),
        'model_config_sha256':hashlib.sha256((ROOT/'model-config.json').read_bytes()).hexdigest(),
        'multistep_deployment_sha256':ready['deployment_sha256'],
        'provenance':'Agent code and model configuration unchanged since both live six-action preflights; setup-only readiness change tested separately on fresh CPU VM.'}
    (ROOT/'environment-preflight.json').write_text(json.dumps(result,indent=2));verify_ready()
    print(json.dumps(result),flush=True)
finally:
    if env:env.close()
