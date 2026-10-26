import hashlib,json,os,subprocess,time
from pathlib import Path

HOME=Path('/mnt/sdb/home/lizh639').resolve()
OLD=HOME/'tb2-three-arm50-scorefix-20261018'
CACHE=OLD/'dependency-cache'
OUT=HOME/'appworld-three-arm30-20261018'/'storage-maintenance'
OUT.mkdir(exist_ok=True)
assert json.loads((OLD/'health.json').read_text())['state']=='finished'
ids=subprocess.check_output(['docker','ps','-aq'],text=True).split()
containers=json.loads(subprocess.check_output(['docker','inspect',*ids])) if ids else []
for c in containers:
    for m in c.get('Mounts',[]):
        p=Path(m['Source']).resolve()
        assert not (p==CACHE or CACHE in p.parents or p in CACHE.parents), ('cache mounted',c['Name'])

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

report={'started':time.time(),'files':[],'restore':'zstd -d ARCHIVE.dependencies.tar.zst -o dependencies.tar; verify SHA256 against this manifest before use'}
manifest=OUT/'compressed-dependency-cache.json'
def save():
    tmp=manifest.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2));os.replace(tmp,manifest)

for p in sorted(CACHE.glob('*/dependencies.tar')):
    assert p.resolve().is_relative_to(CACHE.resolve()) and not p.is_symlink()
    out=p.with_suffix('.tar.zst');tmp=p.with_suffix('.tar.zst.partial')
    assert not out.exists() and not tmp.exists()
    stat=p.stat();sha=digest(p)
    subprocess.run(['zstd','-T1','-3','--quiet',str(p),'-o',str(tmp)],check=True)
    h=hashlib.sha256()
    proc=subprocess.Popen(['zstd','-d','-c','--quiet',str(tmp)],stdout=subprocess.PIPE)
    for b in iter(lambda:proc.stdout.read(4*1024*1024),b''):h.update(b)
    assert proc.wait()==0 and h.hexdigest()==sha
    assert p.stat().st_size==stat.st_size and p.stat().st_mtime_ns==stat.st_mtime_ns
    os.replace(tmp,out)
    row={'original':str(p),'archive':str(out),'original_bytes':stat.st_size,'archive_bytes':out.stat().st_size,'sha256_uncompressed':sha,'verified':True,'original_removed':False}
    report['files'].append(row);save()
    p.unlink();row['original_removed']=True;save()
    print(json.dumps({'task':p.parent.name,'freed_bytes':stat.st_size-out.stat().st_size}),flush=True)
report['completed']=time.time()
report['freed_bytes']=sum(x['original_bytes']-x['archive_bytes'] for x in report['files'])
save()
print(json.dumps({'complete':True,'freed_gib':report['freed_bytes']/2**30}),flush=True)
