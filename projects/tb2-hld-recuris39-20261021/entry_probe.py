import json,secrets,threading,tempfile,os
from pathlib import Path
from spending import Ledger,server_for
async def probe(agent,environment,instruction):
 root=Path(__file__).resolve().parent
 profile=json.loads((root/'budget-profile.json').read_text());profile.update(campaign_limit_microcny=1,task_limit_microcny=1,jobs=['entry-test'])
 with tempfile.TemporaryDirectory(prefix='tb4-entry-') as d:
  ledger=Ledger(Path(d)/'probe.sqlite',profile);token=secrets.token_urlsafe(32);server=server_for(ledger,token,host='10.123.0.1',port=0)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  payload={'key':'offline-dummy-never-transmitted','arm':agent.arm,'instruction':instruction,'proxy':'http://127.0.0.1:1','no_proxy':'10.123.0.1,localhost,127.0.0.1','attempt_id':os.environ['PAIRED_ATTEMPT_ID'],'spending':{'CAMPAIGN_BUDGET_REQUIRED':'1','CAMPAIGN_BUDGET_URL':f'http://10.123.0.1:{server.server_port}','CAMPAIGN_BUDGET_TOKEN':token,'CAMPAIGN_BUDGET_JOB':'entry-test','CAMPAIGN_BUDGET_ARM':'dsh' if agent.arm=='recuris' else 'kz'}}
  cmd=['exec','-T','-w',agent.cwd]
  if environment.default_user is not None:cmd+=['-u',str(environment.default_user)]
  try:
   await environment._run_docker_compose_command(cmd+['main','/opt/node/bin/node','/opt/kz/container-run.mjs'],stdin_data=json.dumps(payload).encode(),check=False,timeout_sec=120)
   result=await agent.exec_as_root(environment,'cat /logs/agent/live/budget-stop.json',timeout_sec=15)
   assert result.return_code==0 and json.loads(result.stdout)['reason']=='per_task_budget_exhausted'
   assert ledger.status()['settled_microcny']==0 and ledger.status()['reserved_microcny']==0
  finally:server.shutdown();server.server_close()
