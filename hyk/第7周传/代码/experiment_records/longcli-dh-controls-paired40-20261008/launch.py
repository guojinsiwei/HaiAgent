"""Fresh local credential via SSH stdin; one launch claim, RAM-only worker."""
import json
import os
import sys
import subprocess
import time
from common import ROOT,save,validate

def main():
    protocol=validate()
    assert not (ROOT/'launch.claim').exists(),'Already launched; inspect status'
    if '--check' in sys.argv:
        print(json.dumps({'ready':True,'trials':protocol['total_trials'],'methods':protocol['methods'],
            'concurrency':protocol['concurrency'],'max_tokens':protocol['max_tokens'],
            'max_input_bytes':protocol['max_input_bytes']}));return
    key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    req=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as response:listing=json.load(response)
    assert any(m['id']=='deepseek-flash' for m in listing['data'])
    os.close(os.open(ROOT/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    # Only this fresh campaign owns the credential and its worker. No old handoff.
    with (ROOT/'worker.log').open('x') as out,(ROOT/'worker-stderr.log').open('x') as err:
        child=subprocess.Popen([sys.executable,'-B',str(ROOT/'run_worker.py')],cwd=ROOT,
            stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True,text=True)
        child.stdin.write(key+'\n');child.stdin.close()
    save(ROOT/'launch.json',{'pid':child.pid,'time':time.time(),'trials':protocol['total_trials'],
                           'credential':'RAM only, fresh input, encrypted SSH stdin'})
    print(json.dumps({'started':True,'pid':child.pid,'trials':protocol['total_trials'],
        'pilot':len(protocol['methods']),'concurrency_after_pilots':protocol['concurrency']}))

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'state':'launch_failed','error_type':type(e).__name__}));raise SystemExit(1)
