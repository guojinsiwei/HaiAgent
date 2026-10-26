"""Fetch the official public Docker image via the local network and create a load archive."""
from pathlib import Path
import concurrent.futures
import gzip
import hashlib
import json
import shutil
import tarfile
import urllib.request
import subprocess
import time
import urllib.error

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None

ROOT=Path(__file__).resolve().parent/'image-transfer'
ROOT.mkdir(exist_ok=True)
REPO='happysixd/osworld-docker'
REGISTRY='https://registry-1.docker.io/v2/'+REPO
with urllib.request.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:'+REPO+':pull',timeout=30) as response:
    token=json.load(response)['token']
headers={'Authorization':'Bearer '+token,'Accept':', '.join([
 'application/vnd.oci.image.index.v1+json','application/vnd.docker.distribution.manifest.list.v2+json',
 'application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json'])}
def metadata(tag):
    request=urllib.request.Request(REGISTRY+'/manifests/'+tag,headers=headers)
    with urllib.request.urlopen(request,timeout=45) as response:raw=response.read()
    return json.loads(raw),hashlib.sha256(raw).hexdigest()
manifest,digest=metadata('latest')
if 'manifests' in manifest:
    candidate=next(x for x in manifest['manifests'] if x.get('platform',{}).get('os')=='linux' and x.get('platform',{}).get('architecture')=='amd64')
    manifest,digest=metadata(candidate['digest'])
(ROOT/'upstream-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Official linux/amd64 manifest sha256:'+digest,flush=True)
def download(desc):
    expected=desc['digest'].split(':')[1];path=ROOT/expected
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        partial=path.with_suffix('.partial')
        opener=urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(urllib.request.Request(REGISTRY+'/blobs/'+desc['digest'],headers=headers),timeout=20) as r:
                partial.write_bytes(r.read())
        except urllib.error.HTTPError as error:
            if error.code not in (302,307):raise
            url=error.headers['Location'];size=desc['size'];chunk_size=1024*1024
            chunks=ROOT/'chunks'/expected;chunks.mkdir(parents=True,exist_ok=True)
            def piece(start):
                end=min(start+chunk_size,size)-1;out=chunks/str(start)
                if out.exists() and out.stat().st_size==end-start+1:return out
                for attempt in range(3):
                    try:
                        request=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'})
                        with urllib.request.urlopen(request,timeout=25) as r:
                            if r.status!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
                                raise RuntimeError('Invalid range response')
                            data=r.read(end-start+2)
                        if len(data)!=end-start+1:raise RuntimeError('Incomplete range')
                        out.write_bytes(data);return out
                    except Exception:
                        if attempt==2:raise
                        time.sleep(1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                pieces=list(pool.map(piece,range(0,size,chunk_size)))
            with partial.open('wb') as out:
                for piece_path in pieces:
                    with piece_path.open('rb') as source:shutil.copyfileobj(source,out)
        if hashlib.sha256(partial.read_bytes()).hexdigest()!=expected:raise RuntimeError('Layer digest mismatch')
        partial.replace(path)
    print('Verified blob '+expected[:12]+' '+str(path.stat().st_size),flush=True)
    return path
config=download(manifest['config'])
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    layers=list(pool.map(download,manifest['layers']))
config_name=config.name+'.json';shutil.copyfile(config,ROOT/config_name)
layer_names=[]
for layer,desc in zip(layers,manifest['layers']):
    name='layers/'+layer.name+'/layer.tar';output=ROOT/name;output.parent.mkdir(parents=True,exist_ok=True)
    opener=gzip.open if 'gzip' in desc['mediaType'] else open
    with opener(layer,'rb') as source,output.open('wb') as out:shutil.copyfileobj(source,out)
    layer_names.append(name)
archive_manifest=[{'Config':config_name,'RepoTags':[REPO+':latest'],'Layers':layer_names}]
(ROOT/'manifest.json').write_text(json.dumps(archive_manifest))
archive=ROOT.parent/'official-osworld-image.tar'
with tarfile.open(archive,'w') as tar:
    for name in ['manifest.json',config_name,*layer_names]:tar.add(ROOT/name,arcname=name)
(ROOT.parent/'vm-image-source.json').write_text(json.dumps({'repository':REPO,'manifest_sha256':digest,
 'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},indent=2))
print('IMAGE_ARCHIVE_READY '+str(archive),flush=True)
