"""New credential on encrypted stdin, inherited anonymous pipe, never a file."""
import json
import os
import sys
import time
from common import ROOT,save
from runner import validate_ready,worker

def main():
    validate_ready()
    key=sys.stdin.readline().strip()
    assert key and not any(c.isspace() for c in key),'Invalid credential'
    # Bounded model-list credential preflight; no completion request or task budget.
    import urllib.request
    request=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
    with urllib.request.urlopen(request,timeout=30) as response:listing=json.load(response)
    assert any(m['id']=='deepseek-flash' for m in listing['data'])
    fd=os.open(ROOT/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    pid=os.fork()
    if pid:
        save(ROOT/'launch.json',{'pid':pid,'time':time.time(),'credential':'RAM only, fresh local hidden input'})
        print(json.dumps({'state':'started','pid':pid,'trials':20,'concurrency_after_pilot':4}));return
    os.setsid()
    with open(os.devnull,'rb') as f:os.dup2(f.fileno(),0)
    with (ROOT/'worker.log').open('x') as f:os.dup2(f.fileno(),1)
    with (ROOT/'worker-stderr.log').open('x') as f:os.dup2(f.fileno(),2)
    try:worker(key)
    except BaseException as exc:
        save(ROOT/'controller-error.json',{'state':'needs_attention','error_type':type(exc).__name__,'time':time.time()})
        os._exit(1)
    os._exit(0)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'state':'launch_failed','error_type':type(exc).__name__}),file=sys.stderr)
        raise SystemExit(1)
