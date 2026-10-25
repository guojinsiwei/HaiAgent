"""Fresh credential: encrypted stdin -> anonymous inherited RAM, never a file."""
import json
import os
import sys
import time
import urllib.request
from common import ROOT,save,validate
from client import NoRedirect
from runner import worker

def main():
    protocol=validate()
    key=sys.stdin.readline().strip()
    assert key and not any(c.isspace() for c in key)
    req=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as r:listing=json.load(r)
    assert any(m['id']==protocol['model'] for m in listing['data'])
    os.close(os.open(ROOT/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    pid=os.fork()
    if pid:
        save(ROOT/'launch.json',{'pid':pid,'time':time.time(),'credential':'fresh hidden input; RAM only'})
        print(json.dumps({'state':'started','trials':protocol['total_trials'],'pid':pid,'mode':'frozen'}));return
    os.setsid()
    with open(os.devnull,'rb') as f:os.dup2(f.fileno(),0)
    with (ROOT/'worker.log').open('x') as f:os.dup2(f.fileno(),1)
    with (ROOT/'worker-stderr.log').open('x') as f:os.dup2(f.fileno(),2)
    try:worker(key)
    except BaseException:
        os._exit(1)
    os._exit(0)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'state':'launch_failed','error_type':type(exc).__name__}),file=sys.stderr)
        raise SystemExit(1)
