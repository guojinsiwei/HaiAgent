import fcntl,json,os,secrets,subprocess,sys,time,urllib.request
from pathlib import Path
from missing2 import HERE,PYTHON,identity,validate
from prepare_missing2 import write

def main():
    with (HERE/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); ready,_=validate()
        if (HERE/'health.json').exists(): raise RuntimeError('Already started; inspect status')
        key=sys.stdin.readline().strip()
        if not key or any(c.isspace() for c in key): raise RuntimeError('Invalid credential')
        req=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
        with urllib.request.urlopen(req,timeout=30) as response: catalog=json.load(response)
        if 'deepseek-flash' not in {m.get('id') for m in catalog.get('data',[])}: raise RuntimeError('Frozen model unavailable')
        secret=Path('/dev/shm')/('lhtb-missing2-'+secrets.token_hex(8));secret.mkdir(mode=0o700)
        credential=secret/'api-key';fd=os.open(credential,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(key)
        key=None
        with (HERE/'guard.log').open('a') as log:
            child=subprocess.Popen([PYTHON,'-B',str(HERE/'missing2.py'),'guard',str(credential)],cwd=HERE,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write(HERE/'guard-started.json',{'pid':child.pid,'identity':identity(child.pid),'time':time.time()})
        for _ in range(90):
            if (HERE/'health.json').exists():
                h=json.loads((HERE/'health.json').read_text())
                if time.time()-h['updated']<30:
                    print(json.dumps({'launched':True,'state':h['state'],'active':h['active'],'protocol_sha256':ready['protocol_sha256']}));return
            if child.poll() is not None:raise RuntimeError('Guard exited; inspect guard.log')
            time.sleep(1)
        raise RuntimeError('Launch unconfirmed')

if __name__=='__main__':
 try:main()
 except Exception as error:
  print(json.dumps({'launched':False,'error_type':type(error).__name__,'message':'Launch not confirmed; inspect before retry'}));sys.exit(2)
