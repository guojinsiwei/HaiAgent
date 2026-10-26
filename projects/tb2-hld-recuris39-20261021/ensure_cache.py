"""Keyless, per-task locked verifier cache preparation; no old cache is modified."""
from pathlib import Path
import fcntl,hashlib,json,os,subprocess
import warm_dependencies as warm
R=Path(__file__).resolve().parent
OLD=R.parent/'tb2-three-arm50-scorefix-20261018/dependency-cache'
def read(p):return json.loads(p.read_text())
def ensure(task):
 assert task in {x['name'] for x in read(R/'tasks.json')['tasks']}
 out=R/'dependency-cache'/task;out.mkdir(parents=True,exist_ok=True)
 with (out/'prepare.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  if (out/'ready.json').exists():return read(out/'ready.json')
  spec=warm.recipe(task)
  matches=[p for p in OLD.glob('*/ready.json') if read(p)['kind']==spec['kind'] and sorted(read(p)['args'])==sorted(spec['args'])]
  if matches:
   src=matches[0];prev=read(src);archive=out/'dependencies.tar'
   with archive.open('wb') as f:subprocess.run(['zstd','-d','-c',str(src.parent/'dependencies.tar.zst')],stdout=f,check=True)
   with archive.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
   assert actual==prev['archive_sha256']
   spec.update(archive_sha256=actual,bytes=archive.stat().st_size,offline_resolution_verified=prev.get('offline_resolution_verified'),source_cache=str(src))
   (out/'ready.json').write_text(json.dumps(spec,indent=2));return spec
  try:return warm.one(task)
  finally:
   name='tb2hr39-cache2-'+task
   p=subprocess.run(['docker','inspect',name,'--format','{{index .Config.Labels "experiment"}}'],capture_output=True,text=True)
   if p.returncode==0 and p.stdout.strip()==R.name:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,check=True)
