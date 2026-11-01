"""Download official pinned verifier tooling, without model calls or task artifacts."""
import hashlib,json,os,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 d=ROOT/'verifier-deps';d.mkdir(exist_ok=True)
 url='https://github.com/astral-sh/uv/releases/download/0.9.5/'
 name='uv-x86_64-unknown-linux-gnu.tar.gz'
 for f in (name,name+'.sha256'):
  p=d/f
  if not p.exists():subprocess.run(['curl','--noproxy','*','-fL','--retry','3','--connect-timeout','20','--max-time','600',url+f,'-o',str(p)],check=True)
 digest=hashlib.sha256((d/name).read_bytes()).hexdigest();assert (d/(name+'.sha256')).read_text().split()[0]==digest
 with tarfile.open(d/name) as t:t.extractall(d/'tools',filter='data')
 uv=d/'tools/uv-x86_64-unknown-linux-gnu/uv'
 env=dict(os.environ,UV_PYTHON_INSTALL_DIR=str(d/'python'),UV_CACHE_DIR=str(d/'download-cache'),UV_HTTP_TIMEOUT='120')
 for k in list(env):
  if 'proxy' in k.lower() or k.endswith(('API_KEY','AUTH_TOKEN')):env.pop(k,None)
 subprocess.run([str(uv),'python','install','3.13'],env=env,check=True,timeout=1200)
 with tarfile.open(ROOT/'verifier-deps.tar.gz','w:gz') as t:
  t.add(d/name,arcname='downloads/'+name);t.add(d/'python',arcname='python')
 files={p.relative_to(d/'python').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (d/'python').rglob('*') if p.is_file() and not p.is_symlink()}
 (ROOT/'verifier-deps-provenance.json').write_text(json.dumps(dict(uv_version='0.9.5',uv_url=url+name,uv_sha256=digest,uv_official_checksum_verified=True,python_installer='uv0.9.5 python install3.13; official default download manifest with checksum verification',python_directories=[p.name for p in (d/'python').iterdir()],python_files=files,archive_sha256=hashlib.sha256((ROOT/'verifier-deps.tar.gz').read_bytes()).hexdigest()),indent=2))
 print('VERIFIER DEPENDENCIES READY',flush=True)
if __name__=='__main__':main()
