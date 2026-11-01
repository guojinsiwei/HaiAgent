"""Explicit one-off retry. Gate failures and solver failures cannot report success."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
os.chdir(root)
job='taotoken-smoke-retry1'
def save(state,**fields):
    target=root/'retry1-status.json'
    temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(state=state,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),job=job,**fields),indent=2))
    temp.replace(target)

def summarize(result,agent):
    if not result: return 'failed_missing_result'
    if result.get('exception_info'): return 'failed_engineering'
    if agent.get('phase')=='live_gate': return 'failed_live_gate'
    if agent.get('exit_code') != 0: return 'failed_agent_graded'
    return 'finished_graded' if result.get('verifier_result') else 'failed_missing_grade'

def main():
    if '--supervise' not in sys.argv:
        if not (root/'retry1-ready.json').exists(): raise SystemExit('Offline acceptance not ready')
        ready=json.loads((root/'retry1-ready.json').read_text())
        if not ready.get('offline_passed'): raise SystemExit('Offline acceptance failed')
        for name, expected in ready['sha256'].items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
                raise SystemExit('Accepted source changed: '+name)
        bundle=json.loads(sys.stdin.readline(16384))
        key=bundle.get('key','')
        if not key or not key.isascii() or any(c.isspace() for c in key): raise SystemExit('Invalid key format')
        if hashlib.sha256(key.encode()).hexdigest()!=bundle.get('input_sha256'): raise SystemExit('Secure input integrity failure')
        with (root/'retry1-launch-once.marker').open('x') as f: f.write('One authorized retry; no automatic restarts.\n')
        env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONPATH=str(root))
        with (root/'retry1-supervisor.log').open('ab',buffering=0) as log:
            child=subprocess.Popen([str(root/'venv/bin/python'),__file__,'--supervise'],env=env,
                stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        print(json.dumps({'started':True,'supervisor_pid':child.pid,'secure_input_integrity':True,'job':job}))
        return
    command=[str(root/'venv/bin/harbor'),'run','-p','task-transport/wal-recovery-ordering',
        '-a','harbor_retry1:KZRetry1','--env','docker','--no-delete','-n','1','-k','1','-r','0',
        '--agent-timeout-multiplier','0.08','--job-name',job,'-o',str(root/'jobs')]
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL)
    while child.poll() is None:
        trials=list((root/'jobs'/job).glob('*/agent'))
        phase='starting'; detail={}
        if trials:
            agent=trials[0]
            gate=agent/'live-gate-result.json'
            exit_file=agent/'agent-exit.json'
            if gate.exists():
                detail['live_gate']=json.loads(gate.read_text())
                phase='solving' if detail['live_gate'].get('passed') else 'gate_failed_grading'
            elif (agent/'live-gate/request-route.jsonl').exists(): phase='live_gate'
            if exit_file.exists():
                detail['agent_exit']=json.loads(exit_file.read_text())
                phase='grading' if detail['agent_exit']['exit_code']==0 else 'agent_failed_grading'
        save(phase,supervisor_pid=os.getpid(),harbor_pid=child.pid,**detail)
        time.sleep(5)
    trials=list((root/'jobs'/job).glob('*/result.json'))
    result=json.loads(trials[0].read_text()) if len(trials)==1 else {}
    files=list((root/'jobs'/job).glob('*/agent/agent-exit.json'))
    agent=json.loads(files[0].read_text()) if len(files)==1 else {}
    save(summarize(result,agent),harbor_exit_code=child.returncode,agent_exit=agent,
        verifier_result=result.get('verifier_result'),exception_info=result.get('exception_info'))

if __name__=='__main__': main()
