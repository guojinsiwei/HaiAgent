"""Single explicitly requested rerun; no scheduling or automatic paid retries."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent/'longcli-hld-full20-triple-20261022'
def read(p):return json.loads(p.read_text())
def validate():
    preflight=read(ROOT/'preflight.json');assert preflight['passed']
    for n,h in preflight['hashes'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n

def run():
    validate()
    from spending import Ledger
    from common import save
    from runner import solve
    profile=read(PARENT/'budget-profile.json');protocol=read(ROOT/'protocol.json')
    ledger=Ledger(PARENT/'spending.sqlite',profile)
    ledger.profile={**profile,'jobs':['hld-hw26-repeat--ap1400_2_hw26'],'requests_per_task':800,'max_output_tokens':32768}
    secret=read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')
    key=secret.get('key') or secret.get('api_key') or secret.get('apiKey');assert key
    result=solve(protocol['tasks'][0],key,ledger)
    save(ROOT/'summary.json',result)

if __name__=='__main__':
    if '--run' in sys.argv:run()
    else:
        validate()
        with (ROOT/'launch-once.marker').open('x') as f:f.write('Fresh HW26 HLD v8; original prompt; 800 requests/32768 output/24 CNY; shared 480 CNY ledger\n')
        with (ROOT/'supervisor.log').open('ab',buffering=0) as log:
            proc=subprocess.Popen([sys.executable,__file__,'--run'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        receipt=dict(pid=proc.pid,started=time.time(),job='hld-hw26-repeat--ap1400_2_hw26',fresh=True,no_hints=True,task_budget_cny=24,shared_campaign_budget_cny=480)
        (ROOT/'launch-receipt.json').write_text(json.dumps(receipt,indent=2))
        print(json.dumps(receipt))
