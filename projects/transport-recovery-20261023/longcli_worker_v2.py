from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import importlib.util,json,os,sys,time,threading
R=Path(__file__).resolve().parent;ROOT=R/'longcli-v2';OLD=R.parent/'longcli-hld-full20-triple-20261022'
sys.path.insert(0,str(ROOT))
from runner import solve
from spending import Ledger
from circuit import Circuit,provider_fault
def read(p):return json.loads(p.read_text())
def save(p,v):
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2));tmp.replace(p)
def main():
    assert read(ROOT/'preflight.json')['passed'] and read(R/'stable-provider.json')['passed']
    with (ROOT/'launch-once.marker').open('x') as f:f.write(str(time.time()))
    profile=read(OLD/'budget-profile.json');ledger=Ledger(OLD/'spending.sqlite',profile)
    rows=read(ROOT/'protocol.json')['tasks'];jobs=[r['budget_job'] for r in rows]
    ledger.profile={**profile,'jobs':jobs,'requests_per_task':800,'max_output_tokens':32768}
    circuit=Circuit(R/'provider-circuit.sqlite');active={};pending=list(rows);done=[];seen=time.time()
    secret=read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')
    key=secret.get('key') or secret.get('api_key') or secret.get('apiKey');assert key
    with ThreadPoolExecutor(max_workers=3) as pool:
        while pending or active:
            with ledger.db() as db:
                failures=db.execute("SELECT reason,created FROM provider_failures WHERE created>? AND reason LIKE 'provider_%' ORDER BY created",(seen,)).fetchall()
            if failures:
                circuit.fail(failures[-1][0]);seen=max(x[1] for x in failures)
            for future,row in list(active.items()):
                if future.done():
                    try:result=future.result()
                    except Exception as e:result=dict(task=row['task'],state='engineering_failure',error=str(e).replace(key,'[REDACTED]')[:500])
                    done.append(result);del active[future]
                    if provider_fault(result) or result.get('engineering_fault'):circuit.fail('longcli_terminal_provider_failure')
            while pending and len(active)<3 and circuit.admit():
                row=pending.pop(0);active[pool.submit(solve,row,key,ledger)]=row
            state='complete' if not active and not pending else 'running' if circuit.admit() else 'provider_paused'
            save(ROOT/'health.json',dict(state=state,pid=os.getpid(),updated=time.time(),concurrency=3,
                 active=[r['task'] for r in active.values()],pending=[r['task'] for r in pending],completed=done,budget=ledger.status(),circuit=circuit.status()))
            if pending or active:time.sleep(5)
    save(ROOT/'summary.json',read(ROOT/'health.json'))
if __name__=='__main__':main()
