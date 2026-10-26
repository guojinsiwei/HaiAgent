from pathlib import Path
import json,hashlib,subprocess,tarfile
root=Path(__file__).resolve().parent
metadata=json.loads((root/'vm-image-source.json').read_text())
digest=hashlib.sha256()
with (root/'official-osworld-image.tar').open('rb') as stream:
    while block:=stream.read(1024*1024):digest.update(block)
assert digest.hexdigest()==metadata['archive_sha256'],'Image archive changed during transfer'
subprocess.run(['docker','load','-i',str(root/'official-osworld-image.tar')],check=True)
value=json.loads(subprocess.check_output(['docker','image','inspect','happysixd/osworld-docker:latest']))[0]
with tarfile.open(root/'official-osworld-image.tar') as archive:
    raw=archive.extractfile('fe8d9a5e5ad6c593d059887ea2c790481b3f32dd42fa961f2441cdbbe2c70cf4.json').read()
assert hashlib.sha256(raw).hexdigest()=='fe8d9a5e5ad6c593d059887ea2c790481b3f32dd42fa961f2441cdbbe2c70cf4'
config=json.loads(raw)
# Docker's containerd store can report a converted manifest ID. Validate all
# uncompressed layer digests and complete execution configuration instead.
assert value['RootFS']['Layers']==config['rootfs']['diff_ids']
assert value['Config']==config['config']
assert value['Architecture']==config['architecture'] and value['Os']==config['os']
(root/'logs/vm-container-image.txt').write_text(value['Id']+'\n')
(root/'logs/docker-image.ready').write_text('official digest verified\n')
print('OFFICIAL_IMAGE_IMPORTED',value['Id'],flush=True)
