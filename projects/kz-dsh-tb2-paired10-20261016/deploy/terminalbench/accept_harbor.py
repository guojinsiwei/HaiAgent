"""Real keyless TerminalBench/Harbor lifecycle acceptance; never launch DSH model."""
import json,os,subprocess,time,sys,uuid,hashlib
from validate_offline import source_hashes
from pathlib import Path
from campaign import command,ROOT,trial
def main():
    label=sys.argv[1] if len(sys.argv)>1 else 'engineering-lifecycle'
    if not label.replace('-','').isalnum():raise ValueError('Invalid local run label')
    arm=sys.argv[2] if len(sys.argv)>2 else 'kz-dsh'
    assert arm in ('dsh','kz-dsh')
    row=dict(task='regex-log',arm=arm,job=label,preflight_attempt_id=uuid.uuid4().hex)
    env=dict(os.environ,PYTHONPATH=str(ROOT),PAIRED_TASK=row['task'],PAIRED_ATTEMPT_ID=row['preflight_attempt_id'],PYTHONDONTWRITEBYTECODE='1')
    for name in ('TAOTOKEN_API_KEY','DEEPSEEK_API_KEY','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN'):env.pop(name,None)
    sources=source_hashes(ROOT/'runtime/kz')
    runtime_hash=hashlib.sha256((ROOT/'runtime-final.tar.gz').read_bytes()).hexdigest()
    start=time.time()
    with (ROOT/(label+'.log')).open('xb') as log:
        result=subprocess.run(command(row,True),cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
    outcome=trial(row,True);outcome.update(harbor_exit=result.returncode,elapsed_seconds=round(time.time()-start,2),paid_calls=0)
    if outcome.get('trial'):
        p=Path(outcome['trial']);lifecycle=json.loads((p/'lifecycle.json').read_text())
        outcome['lifecycle']=lifecycle
        outcome['private_log_readable']=(p/'agent/private-offline-probe.txt').read_text()=='offline probe'
        outcome['passed']=bool(outcome['engineering_clean'] and result.returncode==0 and outcome['private_log_readable'] and lifecycle['stage']=='cleanup_succeeded')
    else:outcome['passed']=False
    outcome.update(source_hashes=sources,runtime_sha256=runtime_hash,arm=arm)
    outcome['passed']=bool(outcome.get('passed') and sources==source_hashes(ROOT/'runtime/kz') and runtime_hash==hashlib.sha256((ROOT/'runtime-final.tar.gz').read_bytes()).hexdigest())
    (ROOT/(label+'-result.json')).write_text(json.dumps(outcome,indent=2))
    print(json.dumps(outcome,indent=2));return 0 if outcome['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
