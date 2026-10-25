"""Prepare a NEW offline repair candidate. Never edit an old run or start an API call."""
import hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=Path('/var/tmp/lizh639-tb4-kz-dsh-paired60-20261013')

def main():
    if (ROOT/'runtime').exists():raise SystemExit('Candidate already prepared; refuse blind overwrite')
    runtime=ROOT/'runtime';runtime.mkdir()
    with tarfile.open(OLD/'runtime-final.tar.gz') as archive:archive.extractall(runtime,filter='data')
    kz=runtime/'kz'
    with tarfile.open(ROOT/'repair-source.tar.gz') as archive:archive.extractall(kz,filter='data')
    # Test-only helpers are intentionally absent from the solver archive.
    with tarfile.open(ROOT/'test-support.tar.gz') as archive:archive.extractall(kz,filter='data')
    for name in ('shared-budget.mjs','route-audit.mjs','route.patch.yml','boot-guard.mjs','container-run.mjs'):shutil.copy2(ROOT/name,kz/name)
    overlay=kz/'.runtime/kz.patch.yml';lines=overlay.read_text().splitlines();result=[];skip=False
    for line in lines:
        if line.strip().startswith(('maxRequests:','maxTools:','wallSeconds:')):continue
        if line.strip()=='costPolicy:':skip=True;continue
        if skip and line.startswith('          '):continue
        skip=False;result.append(line)
        if line.strip()=='full: true':result.append('        budgetDisabled: true')
    overlay.write_text('\n'.join(result)+'\n')
    assert 'budgetDisabled: true' in overlay.read_text()
    for forbidden in ('maxRequests:','maxTools:','wallSeconds:','costPolicy:'):assert forbidden not in overlay.read_text()
    for name in ('tasks.json','official-hashes.json'):shutil.copy2(OLD/name,ROOT/name)
    shutil.copytree(OLD/'official',ROOT/'official')
    # Original files and grader are unchanged; candidate runs must still preflight each task.
    for name,expected in json.loads((ROOT/'official-hashes.json').read_text()).items():
        assert hashlib.sha256((ROOT/'official'/name).read_bytes()).hexdigest()==expected,name
    protocol=json.loads((OLD/'protocol.json').read_text())
    protocol.update(parent_campaign=str(OLD),status='offline_candidate_not_launched',results_reused=False)
    protocol['budget'].update(requests=None,tools=None,solver_seconds=None,outer_cleanup_grace_seconds=None,cost_upper_estimate_cny=None,cost_price_basis=None,mode='unlimited')
    protocol['concurrency']={'total':4,'per_arm':2,'unpaid_preflights':2}
    protocol['task_preflight']='Two unpaid attempts with unique receipts; isolate failed pair and continue others. No automatic paid repeats.'
    protocol['infrastructure_timeouts']='Original Harbor build/setup/verifier timeouts retained. Only paid solver wall timeout disabled in campaign-local entrypoint.'
    protocol['algorithm_role_limits']='Unbounded lifetime Monitor/Advisor quotas; retain cooldown, nonfatal exploration episode limits and two-round Critic completion protocol.'
    protocol['tasks_sha256']=hashlib.sha256((ROOT/'tasks.json').read_bytes()).hexdigest()
    (ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    files=['node','kz/node_modules','kz/src','kz/config','kz/package.json','kz/package-lock.json']
    files+=['kz/'+n for n in ('shared-budget.mjs','route.patch.yml','route-audit.mjs','boot-guard.mjs','container-run.mjs','.runtime/kz.patch.yml','.runtime/transport.patch.yml')]
    subprocess.run(['tar','-czf',str(ROOT/'runtime-final.tar.gz'),'-C',str(runtime),*files],check=True)
    (ROOT/'ready.json').write_text(json.dumps({'passed':False,'reason':'Repair candidate; acceptance and explicit launch still required','paid_calls':0}))
    print(json.dumps({'prepared':True,'paid_calls':0,'budget_mode':'unlimited'}))

if __name__=='__main__':main()
