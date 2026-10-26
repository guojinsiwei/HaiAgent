"""Same official manifest digest, alternate registry transport; no floating substitution."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main(ref):
    old=subprocess.run(['docker','image','inspect',ref,'--format','{{.Id}}'],capture_output=True,text=True,timeout=30)
    if old.returncode==0:
        print(json.dumps(dict(image=ref,existing=old.stdout.strip())));return
    raw=subprocess.check_output(['docker','buildx','imagetools','inspect','--raw',ref],timeout=90)
    manifest=json.loads(raw)
    digest='sha256:'+hashlib.sha256(raw).hexdigest()
    # Pin the exact linux/amd64 child manifest where the reference is an index.
    matches=[m for m in manifest.get('manifests',[]) if m.get('platform',{}).get('os')=='linux' and m.get('platform',{}).get('architecture')=='amd64']
    if manifest.get('manifests'):
        if len(matches)!=1:raise RuntimeError('Ambiguous architecture manifest')
        digest=matches[0]['digest']
    repo=ref.split('@')[0];repo=repo.rsplit(':',1)[0] if ':' in repo.rsplit('/',1)[-1] else repo
    if repo.startswith('docker.io/'):repo=repo[len('docker.io/'):]
    if '/' not in repo:repo='library/'+repo
    if '.' in repo.split('/')[0]:raise RuntimeError('Only Docker Hub mirror is configured')
    mirror='docker.m.daocloud.io/'+repo+'@'+digest
    subprocess.run(['docker','pull','--platform','linux/amd64',mirror],check=True,timeout=600)
    # Mirror path contains the verified immutable digest; Docker verifies content.
    subprocess.run(['docker','tag',mirror,ref],check=True)
    image_id=subprocess.check_output(['docker','image','inspect',ref,'--format','{{.Id}}'],text=True).strip()
    record=dict(original=ref,digest=digest,mirror=mirror,image_id=image_id,time=time.time())
    with (ROOT/'image-transport.jsonl').open('a') as out:out.write(json.dumps(record)+'\n')
    print(json.dumps(record))
if __name__=='__main__':main(sys.argv[1])
