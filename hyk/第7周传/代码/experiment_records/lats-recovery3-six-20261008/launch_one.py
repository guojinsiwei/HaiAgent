"""Start an accepted root exactly once; key on encrypted stdin, RAM only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from common import ROOT,save,sha

def main():
    ready=json.loads((ROOT/'resume-ready.json').read_text())
    assert ready['ready'] and ready['paid_model_calls']==0
    for name,value in ready['hashes'].items():assert sha(ROOT/name)==value,name
    assert not (ROOT/'launch.claim').exists(),'Already launched; inspect status before retrying'
    plan=json.loads((ROOT/'resume-plan.json').read_text())
    if '--check' in sys.argv:
        print(json.dumps({'ready':True,'method':plan['method'],'tasks':len(plan['run_tasks']),'concurrency':plan['concurrency']}));return
    key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    request=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:models=json.load(response)
    assert any(m['id']=='deepseek-flash' for m in models['data'])
    if '--auth-only' in sys.argv:print('{"authentication":true}');return
    os.close(os.open(ROOT/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    with (ROOT/'worker.log').open('x') as out,(ROOT/'worker-stderr.log').open('x') as err:
        child=subprocess.Popen([sys.executable,'-B',str(ROOT/'resume_worker.py')],cwd=ROOT,
            stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True,text=True)
        child.stdin.write(key+'\n');child.stdin.close()
    save(ROOT/'launch.json',{'pid':child.pid,'time':time.time(),'method':plan['method'],'tasks':len(plan['run_tasks'])})
    print(json.dumps({'started':True,'pid':child.pid,'method':plan['method'],'concurrency':plan['concurrency']}))

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'state':'launch_failed','error_type':type(e).__name__}));raise SystemExit(1)
