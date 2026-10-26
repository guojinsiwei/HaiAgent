"""Spaced end-to-end admission checks; canary billed to the original ledger."""
from pathlib import Path
import importlib.util,json,os,secrets,subprocess,threading,time
from circuit import Circuit
from model_proxy import connectivity_check,server
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'longcli-hld-full20-triple-20261022'
def verify():
    circuit=Circuit(ROOT/'provider-circuit.sqlite',cooldown=60,success_gap=10)
    proof=[]
    for _ in range(3):
        ticket=circuit.probe_ticket()
        if ticket is None:
            time.sleep(10);ticket=circuit.probe_ticket()
        assert ticket is not None,'Circuit still cooling down'
        result=connectivity_check();circuit.success(ticket);proof.append(dict(time=time.time(),**result))
        if len(proof)<3:time.sleep(10)
    spec=importlib.util.spec_from_file_location('original_spending',OLD/'spending.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    profile=json.loads((OLD/'budget-profile.json').read_text());ledger=module.Ledger(OLD/'spending.sqlite',profile)
    ledger.profile={**profile,'jobs':['hld-request400--61810_syscall'],'requests_per_task':800,'max_output_tokens':32768}
    token=secrets.token_urlsafe(32);budget=module.server_for(ledger,token,host='127.0.0.1',port=0)
    threading.Thread(target=budget.serve_forever,daemon=True).start()
    proxy=server('127.0.0.1',circuit,ROOT/'canary-proxy.jsonl')
    keydata=json.loads((Path.home()/'.config/appworld-credentials/taotoken-standby.json').read_text())
    key=keydata.get('key') or keydata.get('api_key') or keydata.get('apiKey');assert key
    directory=ROOT/('canary-'+str(int(time.time())))
    env=dict(os.environ,HTTPS_PROXY=f'http://127.0.0.1:{proxy.server_port}',HTTP_PROXY=f'http://127.0.0.1:{proxy.server_port}',
        NO_PROXY='127.0.0.1,localhost',CANARY_LOG=str(directory),CAMPAIGN_BUDGET_REQUIRED='1',
        CAMPAIGN_BUDGET_URL=f'http://127.0.0.1:{budget.server_port}',CAMPAIGN_BUDGET_TOKEN=token,
        CAMPAIGN_BUDGET_JOB='hld-request400--61810_syscall',CAMPAIGN_BUDGET_ARM='acceptance')
    try:
        result=subprocess.run([str(OLD/'runtime/node/bin/node'),'--use-env-proxy',str(ROOT/'canary.mjs')],input=json.dumps(dict(key=key)),
                              env=env,capture_output=True,text=True,timeout=120)
        if result.returncode:
            circuit.fail('canary_failed');raise RuntimeError('Canary failed: '+result.stderr.replace(key,'[REDACTED]')[-1000:])
        assert json.loads(result.stdout)['passed']
        assert circuit.success(ticket,paid_canary=True),'Concurrent failure invalidated canary'
        out=dict(passed=True,created=time.time(),checks=proof,canary=json.loads(result.stdout),
                 ledger=str(OLD/'spending.sqlite'),budget_job='hld-request400--61810_syscall',budget=ledger.status())
        (ROOT/'stable-provider.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
    finally:
        budget.shutdown();budget.server_close();proxy.shutdown();proxy.server_close()
if __name__=='__main__':verify()
