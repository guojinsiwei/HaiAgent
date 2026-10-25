"""Verified publish into existing official grader; never invokes solver or API."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from common import ROOT,save,sha

def read(p):return json.loads(p.read_text()) if p.exists() else {}
def main():
    plan=read(ROOT/'resume-plan.json');allowed={'taco--'+r['task'] for r in plan['run_tasks']}
    if sys.argv[1]=='--start':
        if (ROOT/'relay-grader-launch.json').exists():print('{"already_started":true}');return
        os.close(os.open(ROOT/'relay-grader.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
        with (ROOT/'grading-worker.log').open('x') as out,(ROOT/'grading-stderr.log').open('x') as err:
            child=subprocess.Popen([sys.executable,'-B',str(ROOT/'resume_grader.py')],
                stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,cwd=ROOT)
        save(ROOT/'relay-grader-launch.json',{'pid':child.pid,'model_calls':0});print('{"started":true}');return
    job=sys.argv[1];assert job in allowed
    stage=ROOT/'relay-staging'/job;summary=read(stage/'summary.json')
    assert summary['job']==job and summary['task']==job.split('--',1)[1]
    d=ROOT/'jobs'/job;d.mkdir(exist_ok=True)
    if summary['state']=='awaiting_grade':
        assert summary.get('task_processes_stopped') and not summary.get('engineering_fault') and not summary.get('cleanup_error')
        assert sha(stage/'final-source.tar.gz')==summary['artifact']['sha256']
        target=ROOT/'incoming'/job
        if target.exists():assert sha(target/'final-source.tar.gz')==summary['artifact']['sha256']
        else:stage.rename(target)
    else:assert summary['state']=='engineering_failure'
    save(d/'summary.json',summary)
    n=sum((ROOT/'jobs'/j/'summary.json').exists() for j in allowed)
    save(ROOT/'health.json',{'state':'generation_complete' if n==len(allowed) else 'external_workers_running',
        'active':[],'received':n,'expected':len(allowed),'updated':time.time(),'model_calls':0})
    print(json.dumps({'received':job,'total_received':n}))

if __name__=='__main__':main()
