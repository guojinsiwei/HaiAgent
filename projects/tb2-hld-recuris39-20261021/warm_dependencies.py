"""Build offline verifier caches in disposable, keyless task-image containers."""
import concurrent.futures,hashlib,json,os,re,shlex,subprocess,tarfile,time,tomllib
from pathlib import Path
R=Path(__file__).resolve().parent
def run(args,log,**kw):
 subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True,**kw)
def recipe(task):
 p=R/'dependencies/official/tasks'/task
 script=(p/'tests/test.sh').read_text();flat=script.replace('\\\n',' ')
 if 'uvx ' in flat:
  command=flat[flat.index('uvx '):].split('\n')[0]
  args=shlex.split(command);idx=args.index('pytest',1)
  args=args[:idx]+['pytest','--version']
  args=[a.replace('${COMMIT_HASH}','34bbbfdface3c18e5221aa7de6032d7220c6c6a1') for a in args]
  kind='uv'
 elif 'uv pip install ' in flat:
  install=next(l.strip() for l in flat.splitlines() if l.strip().startswith('uv pip install '))
  venv=next(l.strip() for l in flat.splitlines() if l.strip().startswith('uv venv '))
  venv_args=shlex.split(venv);version=venv_args[venv_args.index('-p')+1]
  packages=shlex.split(install)[3:]
  if any(p.startswith('-') for p in packages):raise ValueError('Unsupported uv pip recipe option')
  args=['uvx','-p',version]+[x for p in packages for x in ['-w',p]]+['pytest','--version'];kind='uv'
 else:
  line=next(l for l in flat.splitlines() if l.startswith('pip install '))
  args=['python','-m','pip','download','--dest','/opt/kz-verifier/wheels']+[a for a in shlex.split(line)[2:] if not a.startswith('--')];kind='pip'
 manifest=tomllib.loads((p/'task.toml').read_text())
 return dict(task=task,kind=kind,args=args,image=manifest['environment']['docker_image'],test_sha256=hashlib.sha256(script.encode()).hexdigest())
def one(task):
 out=R/'dependency-cache'/task;out.mkdir(parents=True,exist_ok=True)
 if (out/'ready.json').exists():return json.loads((out/'ready.json').read_text())
 spec=recipe(task);spec['dependency_index']='https://mirrors.aliyun.com/pypi/simple';name='tb2hr39-cache2-'+task
 with (out/'warm.log').open('a') as log:
  exists=subprocess.run(['docker','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
  if not exists:
   run(['docker','run','-d','--name',name,'--label','experiment=tb2-hld-recuris39-20261021','--user','root','--entrypoint','sleep',spec['image'],'infinity'],log)
   run(['docker','cp',str(R/'verifier-deps.tar.gz'),name+':/tmp/deps.tar.gz'],log)
   setup='mkdir -p /opt/kz-verifier/bin /opt/kz-verifier/wheels; tar -xzf /tmp/deps.tar.gz -C /opt/kz-verifier; tar -xzf /opt/kz-verifier/downloads/uv-x86_64-unknown-linux-gnu.tar.gz --strip-components=1 -C /opt/kz-verifier/bin; rm /tmp/deps.tar.gz'
   run(['docker','exec',name,'sh','-ec',setup],log)
  env=['PATH=/opt/kz-verifier/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','UV_CACHE_DIR=/opt/kz-verifier/cache','UV_PYTHON_INSTALL_DIR=/opt/kz-verifier/python','UV_HTTP_TIMEOUT=60','UV_HTTP_RETRIES=3','UV_CONCURRENT_DOWNLOADS=6','UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple','PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple','PIP_DEFAULT_TIMEOUT=60','PIP_RETRIES=5','HTTP_PROXY=','HTTPS_PROXY=','http_proxy=','https_proxy=']
  cmd=['docker','exec']+sum((['-e',e] for e in env),[])+[name]
  # Online downloads occur only here, before scoring and without a model key.
  run(cmd+spec['args'],log,timeout=2400)
  if spec['kind']=='uv':run(cmd+['/opt/kz-verifier/bin/uvx','--offline']+spec['args'][1:],log,timeout=300)
  temp=out/'dependencies.tar.partial';final=out/'dependencies.tar'
  with temp.open('wb') as f:subprocess.run(['docker','exec',name,'tar','-C','/opt','-cf','-','kz-verifier'],stdout=f,stderr=log,check=True,timeout=1800)
  temp.rename(final)
  spec.update(archive_sha256=hashlib.file_digest(final.open('rb'),'sha256').hexdigest(),bytes=final.stat().st_size,offline_resolution_verified=spec['kind']=='uv')
  (out/'ready.json').write_text(json.dumps(spec,indent=2))
  # Delete only this explicitly created, named warm container after saving cache.
  run(['docker','rm','-f',name],log)
 return spec
def main():
 tasks=list(dict.fromkeys(r['task'] for r in json.loads((R/'repair-plan.json').read_text())))
 with concurrent.futures.ThreadPoolExecutor(2) as pool:
  fs={pool.submit(one,t):t for t in tasks}
  for f in concurrent.futures.as_completed(fs):
   try:r=f.result();print(json.dumps({'task':r['task'],'ready':True,'bytes':r['bytes']}),flush=True)
   except Exception as e:print(json.dumps({'task':fs[f],'ready':False,'error':str(e)}),flush=True)
if __name__=='__main__':main()
