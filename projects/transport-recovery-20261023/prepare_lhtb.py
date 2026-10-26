"""Isolated repair deployment, same frozen algorithms/tasks and original ledger."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time
R=Path(__file__).resolve().parent;P=R.parent/'lhtb-hld-v8-recuris24-20261022';O=R/'lhtb'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,indent=2))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def once(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def replace_file(p,text):
    if p.exists():p.unlink()
    p.write_text(text)
def main():
    O.mkdir(exist_ok=False)
    old=read(P/'health.json');rows=[]
    for row in old['rows']:
        result=row.get('result',{});provider=(result.get('stops',{}).get('provider-stop.json') or {})
        if provider.get('kind')!='transport' and row.get('state')!='engineering_failure':continue
        item=dict(row);item.update(state='pending',original_state=row['state'],source_trial=result.get('trial'),
            restore_progress=result.get('shared_usage',{}).get('tools',0)>0,
            remaining_seconds=max(1,10800-int(row.get('ended',row.get('paid_started',0))-row.get('paid_started',row.get('ended',0)))))
        if not row.get('paid_started'):item['remaining_seconds']=10800
        for key in ['started','paid_started','ended','preflight','live']:item.pop(key,None)
        rows.append(item)
    assert len(rows)==42 and sum(r['restore_progress'] for r in rows)==6
    save(O/'recovery-rows.json',rows)
    # Progress-bearing runs first, then jobs whose first API request never succeeded.
    rows.sort(key=lambda r:(not r['restore_progress'],r['job']))
    save(O/'queue.json',dict(rows=rows))
    for folder in ['upstream','venv','image-cache']:(O/folder).symlink_to(P/folder,target_is_directory=True)
    for filename in ['host_agent.py','spending.py','agents.py','campaign.py','entry_harbor.py','budget-profile.json','protocol.json','input-manifest.json']:
        shutil.copy2(P/filename,O/filename)
    for filename in ['python-runtime.tar.gz']:os.link(P/filename,O/filename)
    shutil.copytree(P/'environment-locks',O/'environment-locks')
    shutil.copytree(P/'vendor-src',O/'vendor-src',copy_function=os.link,symlinks=True)
    shutil.copytree(P/'bundle',O/'bundle',copy_function=os.link,symlinks=True)
    for name in ['circuit.py','model_proxy.py','replay_tools.py','lhtb_recovery_hook.py']:(O/name).symlink_to(R/name)
    replace_file(O/'bundle/kz/provider-guard.mjs',(R/'provider-guard.mjs').read_text())
    entry=(O/'bundle/kz/container-run.mjs').read_text()
    entry=once(entry,"args.push('--json','-');","if(bundle.resume_session)args.push('--session-id',bundle.resume_session);\nargs.push('--json','-');")
    entry=once(entry,'child.stdin.end(bundle.instruction)',"child.stdin.end(bundle.resume_session?'Continue the original task from the recovered workspace and session. Inspect the current workspace state after connection recovery.':bundle.instruction)")
    replace_file(O/'bundle/kz/container-run.mjs',entry)
    spending=(O/'spending.py').read_text()
    spending=once(spending,"self.ledger = Ledger(Path(root)/'spending.sqlite', self.profile)","self.ledger = Ledger(Path("+repr(str(P))+ ")/'spending.sqlite', self.profile)")
    (O/'spending.py').write_text(spending)
    agents=(O/'agents.py').read_text()
    agents=once(agents,"        (self.logs_dir.parent/'operator-container.json').write_text(json.dumps(dict(containers=containers,network=self.network,gateway=self.gateway),indent=2))",
        "        (self.logs_dir.parent/'operator-container.json').write_text(json.dumps(dict(containers=containers,network=self.network,gateway=self.gateway),indent=2))\n        if os.environ.get('LHTB_OFFLINE')!='1':\n            from lhtb_recovery_hook import restore\n            await restore(self,environment)")
    agents=once(agents,"if not hasattr(self,'deadline'):self.deadline=time.monotonic()+10800","if not hasattr(self,'deadline'):self.deadline=time.monotonic()+getattr(self,'recovery_remaining',10800)")
    agents=once(agents,"payload=dict(key=key,arm=self.arm,instruction=instruction,phase=phase,remaining_seconds=remaining,","payload=dict(key=key,arm=self.arm,instruction=instruction,phase=phase,remaining_seconds=remaining,resume_session=getattr(self,'resume_session',None) if phase==0 else None,")
    # If the provider fails while an offline restore is in progress, wait for
    # verified recovery instead of making the first paid call into that outage.
    agents=once(agents,"        result=await self.invoke(payload)","        from circuit import Circuit\n        gate=Circuit(ROOT.parent/'provider-circuit.sqlite')\n        while not gate.admit():await asyncio.sleep(10)\n        result=await self.invoke(payload)")
    (O/'agents.py').write_text(agents)
    campaign=(O/'campaign.py').read_text()
    campaign=once(campaign,"from spending import BudgetService","from spending import BudgetService\nfrom circuit import Circuit,provider_fault\nfrom model_proxy import connect as stable_connect")
    campaign=once(campaign,"PY=ROOT/'venv/bin/python'","PY=ROOT/'venv/bin/python'\nCIRCUIT=Circuit(ROOT.parent/'provider-circuit.sqlite')")
    campaign=once(campaign,"try:up=socket.create_connection(('api.taotoken.net',443),20)\n        except OSError:self.send_error(502);return", "try:up=stable_connect('api.taotoken.net',443)\n        except OSError:\n            CIRCUIT.fail('model_proxy_connect_failed')\n            self.send_error(502);return")
    campaign=once(campaign,"        continuation=(result.get('agent_result') or {}).get('metadata'),offline=offline)","        continuation=(result.get('agent_result') or {}).get('metadata'),offline=offline)\n    out['scoring_clean']=clean\n    if not offline and provider_fault(out):out['engineering_clean']=False\n    if not offline and (out.get('continuation') or {}).get('agent_return_code') not in (None,0) and not any((stops.get(n) or {}).get('reason') in ('per_task_budget_exhausted','per_task_request_limit','per_task_tool_limit','solver_wall_limit') for n in ['budget-stop.json','limit-stop.json','wall-limit.json']):out['engineering_clean']=False")
    campaign=once(campaign,"    if clean:\n        for item", "    if clean and (offline or list(path.parent.glob('submission-snapshot-*.json'))):\n        for item")
    campaign=once(campaign,"rows=read(ROOT/'queue.json')['rows'];active={}","rows=read(ROOT/'queue.json')['rows'];active={};seen_provider_failure=time.time()")
    campaign=once(campaign,"                busy=collections.Counter(row['arm'] for row in active.values())", "                with budget.ledger.db() as db:\n                    failures=db.execute(\"SELECT reason,created FROM provider_failures WHERE created>? AND reason LIKE 'provider_%' ORDER BY created\",(seen_provider_failure,)).fetchall()\n                if failures:\n                    CIRCUIT.fail(failures[-1][0]);seen_provider_failure=max(x[1] for x in failures)\n                busy=collections.Counter(row['arm'] for row in active.values())")
    campaign=once(campaign,"                    if len(active)>=6:break","                    if len(active)>=6 or not CIRCUIT.admit():break")
    campaign=once(campaign,"snapshot(rows,active,budget,'finished' if finished else 'running')","snapshot(rows,active,budget,'finished' if finished else 'running' if CIRCUIT.admit() else 'provider_paused')")
    campaign=once(campaign,"concurrency_limit=6,active=", "concurrency_limit=6,circuit=CIRCUIT.status(),active=")
    # Keep previous outputs and metadata in the row; replace only the new result.
    campaign=once(campaign,"        validate();row.update(state='solving',paid_started=time.time())", "        validate()\n        while not CIRCUIT.admit():time.sleep(10)\n        row.update(state='solving',paid_started=time.time())")
    campaign=once(campaign,"result=run_trial(row,False,budget.token,budget.url);row.update(result=result,state='done' if result['engineering_clean'] else 'engineering_failure',ended=time.time())", "result=run_trial(row,False,budget.token,budget.url);row.update(result=result,state='done' if result['engineering_clean'] else 'engineering_failure',ended=time.time())\n        if provider_fault(result):CIRCUIT.fail('terminal_provider_failure')")
    # Result-classification bug fixed: score presence cannot hide transport stops.
    (O/'campaign.py').write_text(campaign)
    entry=(O/'entry_harbor.py').read_text()
    entry="""from harbor.trial.trial import Trial
from lhtb_recovery_hook import snapshot
_verification=Trial._run_verification
async def _with_snapshot(self):
    await snapshot(self)
    return await _verification(self)
Trial._run_verification=_with_snapshot
"""+entry
    (O/'entry_harbor.py').write_text(entry)
    for file in O.glob('*.py'):compile(file.read_text(),str(file),'exec')
    lock=read(P/'algorithm-source-lock.json')
    for files in lock.values():
        for name,digest in files.items():assert sha(O/'bundle'/name)==digest,name
    subprocess.run([str(O/'bundle/node/bin/node'),'--check',str(O/'bundle/kz/container-run.mjs')],check=True)
    subprocess.run(['tar','-czf',str(O/'runtime-final.tar.gz'),'-C',str(O/'bundle'),'node','kz','recuris-dsh','dsh-baselines'],check=True)
    manifest={str(p.relative_to(O)):sha(p) for p in O.glob('*.py')}
    manifest.update({name:sha(O/name) for name in ['runtime-final.tar.gz','budget-profile.json','recovery-rows.json']})
    save(O/'ready.json',dict(passed=True,files=manifest,model_calls=0,source_frozen=True,shared_original_ledger=True))
    save(O/'repair-protocol.json',dict(tasks=42,restore_progress=6,fresh_start_or_preflight_failure=36,concurrency=6,per_arm=3,
         original_ledger=str(P/'spending.sqlite'),per_task_cny=24,campaign_cny=1152,original_job_ids_retained=True,historical_results_preserved=True))
    print(json.dumps(dict(prepared=True,tasks=42,resume=6)))
if __name__=='__main__':main()
