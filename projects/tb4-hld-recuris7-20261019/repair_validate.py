"""Two real payments lifecycles; no credentials and no model calls."""
import json,os,subprocess,sys,uuid
from pathlib import Path
import campaign
R=Path(__file__).resolve().parent
results=[]
for agent,label in [('agents:OfflineHLD','ordinary'),('repair_probes:StoppedMain','stopped-main')]:
    row=dict(job='repair-v1-'+label,arm='hld',task='payments-pipeline-fix',preflight_attempt_id=uuid.uuid4().hex)
    env={**os.environ,'PAIRED_TASK':row['task'],'PAIRED_ATTEMPT_ID':row['preflight_attempt_id'],'PYTHONPATH':str(R),'SCORE_SNAPSHOT_ACCEPTANCE':'1'}
    for key in ['TAOTOKEN_API_KEY','ENTRY_ACCEPTANCE','CAMPAIGN_BUDGET_REQUIRED']:env.pop(key,None)
    cmd=campaign.command(row,True);cmd[cmd.index('-a')+1]=agent
    with (R/'repair-v1'/('validation-'+label+'.log')).open('w') as out:
        p=subprocess.run(cmd,env=env,stdout=out,stderr=out,timeout=1800)
    result=campaign.trial(row,True);result.update(label=label,exit_code=p.returncode)
    t=Path(result['trial']);result['snapshot_present']=(t/'submission-snapshot.json').is_file()
    if label=='stopped-main':result['private_log_recovered']=(t/'agent/private-marker').read_text().strip()=='recovery-marker'
    results.append(result)
    passed=all(x['engineering_clean'] and x['exit_code']==0 and x['snapshot_present'] and x.get('private_log_recovered',True) for x in results)
    (R/'repair-v1/acceptance.json').write_text(json.dumps(dict(passed=passed and len(results)==2,checks=results,paid_calls=0),indent=2))
    print(json.dumps(result),flush=True)
    if not passed:sys.exit(1)
