"""Public Go artifact cache and isolated dependency-only preparation. No model calls."""
import hashlib,json,os,re,shlex,subprocess,sys,threading,time,urllib.error,urllib.request,urllib.parse,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
R=Path(__file__).resolve().parent
CACHE=R/'dependency-cache/go'
LOCKS={};GUARD=threading.Lock()

def artifact_path(raw):
 raw=urllib.parse.unquote(raw,errors='strict')
 if not re.fullmatch(r'/[A-Za-z0-9_!@./+~%-]+',raw) or '%' in raw or '..' in raw.split('/'):
  raise ValueError('Invalid artifact path')
 if not ('/@v/' in raw or raw.endswith('/@latest') or raw.startswith('/sumdb/sum.golang.org/')):
  raise ValueError('Only module and signed checksum artifacts are served')
 p=CACHE/raw.lstrip('/')
 assert p.resolve().is_relative_to(CACHE.resolve())
 return p

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  try:p=artifact_path(self.path)
  except ValueError:self.send_error(400);return
  with GUARD:lock=LOCKS.setdefault(str(p),threading.Lock())
  try:
   with lock:
    if not p.is_file():
     error=None
     for attempt in range(3):
      try:
       upstream=('https://goproxy.cn' if self.path.startswith('/sumdb/sum.golang.org/') else 'https://proxy.golang.org')+self.path
       with urllib.request.urlopen(upstream,timeout=30) as response:
        data=response.read(256*1024*1024+1)
       if len(data)>256*1024*1024:raise ValueError('Artifact exceeds cache limit')
       p.parent.mkdir(parents=True,exist_ok=True)
       tmp=p.with_name(p.name+'.partial-'+uuid.uuid4().hex);tmp.write_bytes(data);tmp.replace(p)
       entry=dict(path=self.path,url=upstream,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),time=time.time())
       with GUARD:
        with (R/'dependency-cache/fetches.jsonl').open('a') as f:f.write(json.dumps(entry)+'\n')
       error=None;break
      except urllib.error.HTTPError as exc:
       if exc.code in (400,404,410):self.send_error(exc.code);return
       error=exc
      except Exception as exc:error=exc
      time.sleep(attempt+1)
     if error:raise error
    size=p.stat().st_size
   self.send_response(200);self.send_header('Content-Length',str(size));self.end_headers()
   with p.open('rb') as f:
    while data:=f.read(1024*1024):self.wfile.write(data)
  except (BrokenPipeError,ConnectionResetError):pass
  except Exception:self.send_error(502)

def serve():
 import runner
 CACHE.mkdir(parents=True,exist_ok=True)
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 runner.save(R/'dependency-cache/service.json',dict(pid=os.getpid(),url=f'http://127.0.0.1:{server.server_port}',started=time.time()))
 server.serve_forever()

def service_url():
 import runner
 doc=runner.read(R/'dependency-cache/service.json')
 pid=doc.get('pid');cmd=Path('/proc',str(pid),'cmdline')
 if not cmd.exists() or b'dependencies.py' not in cmd.read_bytes():raise RuntimeError('Dependency cache service is unavailable')
 return doc['url']

def mount():
 CACHE.mkdir(parents=True,exist_ok=True)
 return (CACHE,'/opt/public-go-cache',True)

def install_go(name,solver=False):
 import runner
 cmd='cache=$(go env GOMODCACHE) && mkdir -p "$cache/cache/download" && cp -an /opt/public-go-cache/. "$cache/cache/download/"'
 if solver:cmd+=' && go env -w GOPROXY=file:///opt/public-go-cache GOSUMDB=off'
 p=runner.execute(name,cmd,180,capture_output=True,text=True)
 if p.returncode:raise RuntimeError('Cannot install verified Go cache: '+p.stderr[-400:])

def prepare(task,name,solver=False):
 """Fetch declared modules in a keyless throwaway image; copy only public artifacts."""
 import runner
 cwd=runner.cwd_of(name)
 probe=runner.execute(name,f'cd {shlex.quote(cwd)} && command -v go >/dev/null && test -f go.mod',30,capture_output=True)
 if probe.returncode:return dict(kind='image_bundled',go=False)
 identity=runner.execute(name,f'cd {shlex.quote(cwd)} && sha256sum go.mod && if test -f go.sum; then sha256sum go.sum; fi',30,capture_output=True,text=True)
 if identity.returncode:raise RuntimeError('Cannot fingerprint dependency manifests')
 digest=hashlib.sha256((task['image_id']+identity.stdout).encode()).hexdigest()
 folder=R/'dependency-cache/preparations'/digest;folder.mkdir(parents=True,exist_ok=True)
 with GUARD:lock=LOCKS.setdefault('prepare:'+digest,threading.Lock())
 with lock:
  receipt=runner.read(folder/'ready.json')
  if not receipt.get('ready'):
   builder=runner.LABEL+'-deps-'+uuid.uuid4().hex[:10]
   runner.create(task,builder,network='host')
   try:
    base=runner.cwd_of(builder)
    for filename in ['go.mod','go.sum']:
     target=folder/filename
     p=subprocess.run(['docker','cp',name+':'+cwd+'/'+filename,str(target)],capture_output=True)
     if p.returncode:
      if filename=='go.mod':raise RuntimeError('Missing go.mod')
      continue
     runner.run(['docker','cp',str(target),builder+':'+base+'/'+filename],stdout=subprocess.DEVNULL)
    install_go(builder)
    url=service_url()
    sumdb=shlex.quote('sum.golang.org '+url+'/sumdb/sum.golang.org')
    command=f'cd {shlex.quote(base)} && env GOPROXY={shlex.quote(url)} GOSUMDB={sumdb} GONOSUMDB= GOPRIVATE= GOTOOLCHAIN=local go mod download all'
    with (folder/'download.log').open('wb') as f:
     p=runner.execute(builder,command,900,stdout=f,stderr=f)
    if p.returncode:raise RuntimeError('Dependency preparation failed: '+str(folder/'download.log'))
    receipt=dict(ready=True,image_id=task['image_id'],manifest_sha256=digest,time=time.time(),model_calls=0,checksum_verification='Go sum database and original go.sum',source='proxy.golang.org')
    runner.save(folder/'ready.json',receipt)
   finally:runner.remove(builder)
 install_go(name,solver=solver)
 return receipt

if __name__=='__main__':
 if '--serve' in sys.argv:serve()
 else:raise SystemExit('Use --serve, or import prepare()')
