"""Real keyless TerminalBench/Harbor lifecycle acceptance; never launch DSH model."""
import json,os,subprocess,time,sys
from pathlib import Path
from campaign import command,ROOT,trial
def main():
    label=sys.argv[1] if len(sys.argv)>1 else 'ec2-lifecycle-payments'
    if not label.replace('-','').isalnum():raise ValueError('Invalid local run label')
    row=dict(task='payments-pipeline-fix',arm='kz-dsh',job=label)
    env=dict(os.environ,PYTHONPATH=str(ROOT),PAIRED_TASK=row['task'],PYTHONDONTWRITEBYTECODE='1')
    for name in ('TAOTOKEN_API_KEY','DEEPSEEK_API_KEY','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN'):env.pop(name,None)
    start=time.time()
    with (ROOT/(label+'.log')).open('xb') as log:
        result=subprocess.run(command(row,True),cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
    outcome=trial(row,True);outcome.update(harbor_exit=result.returncode,elapsed_seconds=round(time.time()-start,2),paid_calls=0)
    if outcome.get('trial'):
        p=Path(outcome['trial']);lifecycle=json.loads((p/'lifecycle.json').read_text())
        outcome['lifecycle']=lifecycle
        outcome['private_log_readable']=(p/'agent/private-offline-probe.txt').read_text()=='offline probe'
        outcome['passed']=bool(outcome['engineering_clean'] and result.returncode==0 and outcome['private_log_readable'] and lifecycle['stage']=='finalized')
    else:outcome['passed']=False
    (ROOT/(label+'-result.json')).write_text(json.dumps(outcome,indent=2))
    print(json.dumps(outcome,indent=2));return 0 if outcome['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
