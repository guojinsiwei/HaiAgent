"""Finite zero-model provisioning job. Never starts paid trials."""
import json,time
from pathlib import Path
import docker
ROOT=Path(__file__).resolve().parent
client=docker.from_env(timeout=120)
for _ in range(180):
    try:client.images.get('suz-android-cpu:20261026');break
    except docker.errors.ImageNotFound:time.sleep(10)
else:raise RuntimeError('Android image build not completed in 30 minutes')
out=ROOT/'android-bootstrap';out.mkdir(exist_ok=True)
try:
    c=client.containers.get('suz-mb-android-bootstrap')
    assert c.labels.get('experiment')=='suz-multibench-20261026'
    assert c.status in ['created','running'],'Exited bootstrap requires diagnosis before replay'
except docker.errors.NotFound:
    c=client.containers.create('suz-android-cpu:20261026',command=['python','-u','/opt/harness/prepare_android.py'],name='suz-mb-android-bootstrap',runtime='runc',mem_limit='10g',nano_cpus=6000000000,devices=['/dev/kvm:/dev/kvm:rwm'],volumes={str(ROOT):{'bind':'/campaign','mode':'rw'},str(out):{'bind':'/output','mode':'rw'},str(ROOT/'harness'):{'bind':'/opt/harness','mode':'ro'}},labels={'owner':'lizh639','experiment':'suz-multibench-20261026'})
if c.status=='created':c.start()
print('BOOTSTRAP_CONTAINER',c.name,flush=True)
deadline=time.monotonic()+2700
while time.monotonic()<deadline:
    c.reload()
    if c.status in ['exited','dead']:break
    time.sleep(10)
else:
    c.stop(timeout=30);raise RuntimeError('Android bootstrap timeout; state retained')
(out/'container.log').write_bytes(c.logs())
report=json.loads((out/'android-preflight.json').read_text())
assert report['passed'] and len(report['checks'])==10
assert c.attrs['State']['ExitCode']==0
image=c.commit(repository='suz-android-ready',tag='20261026',conf={'Cmd':['python','-u','/opt/harness/worker.py']})
(out/'frozen-image.json').write_text(json.dumps({'id':image.id,'bootstrap':c.name,'gpu':False,'model_calls':0},indent=2))
print('ANDROID_READY_IMAGE',image.id,flush=True)

