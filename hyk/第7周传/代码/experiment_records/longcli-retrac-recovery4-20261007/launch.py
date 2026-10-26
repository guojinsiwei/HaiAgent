"""Fresh local hidden key input only; never use an existing worker's key."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from common import ROOT,save,validate

def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');a=p.parse_args()
    validate();assert not (ROOT/'launch.claim').exists(),'Already launched; do not duplicate trials'
    key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
    req=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
    with urllib.request.urlopen(req,timeout=30) as r:models=json.load(r)
    assert any(m['id']=='deepseek-flash' for m in models['data'])
    if a.check_only:print(json.dumps({'state':'credential_preflight_passed','paid_model_calls':0}));return
    os.close(os.open(ROOT/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    fd,name=tempfile.mkstemp(prefix='longcli-retrac-',dir='/dev/shm');os.fchmod(fd,0o600)
    try:
        with os.fdopen(fd,'w') as f:f.write(key)
        scratch=ROOT/'host-tmp';scratch.mkdir(exist_ok=True)
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1',
             'TMPDIR':str(scratch)}
        with (ROOT/'worker.log').open('x') as out,(ROOT/'worker-stderr.log').open('x') as err:
            worker=subprocess.Popen([sys.executable,'-B',str(ROOT/'runner.py'),'--credential-file',name],
                stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=env,cwd=ROOT,start_new_session=True)
        save(ROOT/'launch.json',{'state':'starting','pid':worker.pid,'time':time.time(),'concurrency':2,
                                 'maximum_concurrency':4,'canary_first':True,'new_input_key':True})
        with (ROOT/'grading.log').open('x') as out,(ROOT/'grading-stderr.log').open('x') as err:
            grader=subprocess.Popen([sys.executable,'-B',str(ROOT/'grading_worker.py')],
                stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=env,cwd=ROOT,start_new_session=True)
        save(ROOT/'grading-launch.json',{'pid':grader.pid,'model_calls':0,'time':time.time()})
        time.sleep(2);assert worker.poll() is None
        print(json.dumps({'state':'started','pid':worker.pid,'concurrency':2,'maximum_concurrency':4,
                          'canary_first':True,'engineering_fail_fast':True,'grading_model_calls':0}))
    finally:
        if 'worker' not in locals():Path(name).unlink(missing_ok=True)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'state':'launch_failed_or_uncertain','error_type':type(e).__name__}),file=sys.stderr)
        raise SystemExit(1)
