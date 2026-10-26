"""Start only the accepted fresh TACO arm; credential arrives on stdin and stays in RAM."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from common import ROOT,save


def validate():
    ready=json.loads((ROOT/'resume-ready.json').read_text())
    assert ready['ready'] and ready['paid_model_calls']==0 and ready['remaining']==20
    for name,expected in ready['hashes'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    assert not (ROOT/'launch.claim').exists(), 'Already launched; inspect status first'
    assert not (ROOT/'taco-pool.json').exists(), 'Shared cache would violate task isolation'
    plan=json.loads((ROOT/'resume-plan.json').read_text())
    assert plan['method']=='taco' and len(plan['run_tasks'])==20 and not plan['preserved']
    return plan


def main():
    plan=validate()
    if '--check' in sys.argv:
        print(json.dumps({'ready':True,'method':'taco','tasks':len(plan['run_tasks']),
                          'old_results_reused':0}));return
    key=sys.stdin.readline().strip()
    assert key and not any(c.isspace() for c in key), 'Invalid credential'
    request=urllib.request.Request('https://api.deepseek.com/models',
        headers={'Authorization':'Bearer '+key})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
        listing=json.load(response)
    assert any(model['id']=='deepseek-flash' for model in listing['data'])
    os.close(os.open(ROOT/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    with (ROOT/'worker.log').open('x') as out,(ROOT/'worker-stderr.log').open('x') as err:
        child=subprocess.Popen([sys.executable,'-B',str(ROOT/'resume_worker.py')],cwd=ROOT,
            stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True,text=True)
        child.stdin.write(key+'\n');child.stdin.close()
    save(ROOT/'launch.json',{'pid':child.pid,'time':time.time(),'method':'taco',
                             'tasks':20,'credential':'RAM-only anonymous pipe'})
    print(json.dumps({'state':'started','pid':child.pid,'tasks':20,'concurrency':1}))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'state':'launch_failed','error_type':type(exc).__name__}),file=sys.stderr)
        raise SystemExit(1)
