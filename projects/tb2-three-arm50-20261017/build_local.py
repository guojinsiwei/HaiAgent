"""Assemble a new independent 150-trial campaign without copying prior admissions."""
import json,shutil,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROJECTS=ROOT.parent
BASE=PROJECTS/'kz-dsh-tb2-transport1-20261017'
NATIVE=PROJECTS/'kz-native-tb2-tls3-20261017'
for name in ('campaign.py','agents.py','host_agent.py','entry_harbor.py','lifecycle_guard.py','trial_runner.py','receipts.py','storage.py','recovery.py','spending.py','verifier_setup.py','build_runtime.py','test_bounded_ledger.py','test_bounded_transport.mjs','test_deadline.mjs','test-provider-guard.mjs','deadline.mjs','provider-guard.mjs','shared-budget.mjs','spending-client.mjs','messages-protocol.mjs','container-run.mjs'):
    shutil.copy2(BASE/name,ROOT/name)
shutil.copy2(NATIVE/'connection_probe.py',ROOT/'connection_probe.py')
p=ROOT/'verifier_setup.py'
v=p.read_text().replace(" if name not in TASKS:raise RuntimeError('Unapproved verifier dependency bootstrap')", " approved={t['name'] for t in json.loads((ROOT/'tasks.json').read_text())['tasks']}\n if name not in approved:raise RuntimeError('Task outside frozen selection')\n script=(verifier.task.paths.task_dir/'tests/test.sh').read_text()\n # Only bootstrap the matching official uv installer; other recipes run unchanged.\n if 'astral.sh/uv/0.9.5' not in script:return")
p.write_text(v)
native_campaign=(NATIVE/'campaign.py').read_text()
helpers=native_campaign[native_campaign.index('def trial('):native_campaign.index('def proxy_module(')]
(ROOT/'native_results.py').write_text('import collections,json\nfrom pathlib import Path\nfrom receipts import read_receipt,lifecycle_status,valid_reward\nROOT=Path(__file__).resolve().parent\ndef read(p):\n try:return json.loads(Path(p).read_text())\n except (FileNotFoundError,ValueError):return {}\n'+helpers)
agents=(ROOT/'agents.py').read_text()+'\n'+(NATIVE/'agents.py').read_text().split('class OfflineTimeout')[0]
(ROOT/'agents.py').write_text(agents)
p=ROOT/'entry_harbor.py';p.write_text(p.read_text().replace("'agents:DSH',","'agents:Native','agents:OfflineNative','agents:DSH',"))
s=(ROOT/'campaign.py').read_text().replace('PORT=28665','PORT=28705').replace('port=28666','port=28706')
s=s.replace("def trial(row,offline=False):", "def trial(row,offline=False):\n    if row['arm']=='native-kz':\n        from native_results import trial as collect_native\n        return collect_native(row,offline)")
s=s.replace('def live_snapshot(row):',"def live_snapshot(row):\n    if row['arm']=='native-kz':\n        from native_results import live_snapshot as native_snapshot\n        return native_snapshot(row)")
s=s.replace("    return [PY,str(ROOT/'trial_runner.py')", "    if row['arm']=='native-kz':agent='OfflineNative' if offline else 'Native'\n    return [PY,str(ROOT/'trial_runner.py')")
start=s.index('def disk_need(');end=s.index('def command(',start)
s=s[:start]+'''def disk_need(task):
    r=next(r for r in read(ROOT/'tasks.json')['tasks'] if r['name']==task)
    e=r.get('environment',{});raw=e.get('storage','10G')
    gib=float(str(raw).upper().removesuffix('IB').removesuffix('B').removesuffix('G')) if str(raw).upper().endswith(('G','GB','GIB')) else 10
    return max(12*1024**3,2*int(e.get('storage_mb',gib*1024))*1024**2)

def space_ready(task,active):
    # Keep 12 GiB free beyond conservative, task-specific concurrent reservations.
    from recovery import owned_alive
    external=sum(len(h.get('active',[])) for p in ROOT.parent.glob('tb2-*/health.json') if p.parent!=ROOT for h in [read(p)] if owned_alive(h.get('supervisor_identity')))
    quarantined=read(ROOT/'quarantine.json').get('jobs',[])
    reserve=disk_need(task)+sum(disk_need(x['row']['task']) for x in active.values())+(external+len(quarantined))*30*1024**3
    return shutil.disk_usage('/var/lib/docker').free>=12*1024**3+reserve and shutil.disk_usage(ROOT).free>=4*1024**3

''' +s[end:]
s=s.replace("candidates(rows,{v['row']['arm'] for v in active.values()})","candidates(rows,[v['row']['arm'] for v in active.values()])")
s=s.replace('if len(active)>=1:break','if len(active)>=6:break').replace("if any(v['row']['arm']==row['arm'] for v in active.values()):continue","if sum(v['row']['arm']==row['arm'] for v in active.values())>=2:continue")
s=s.replace("                        row.update(state='reconciliation_required',reason='missing_or_active_runner_receipt')\n                        recovery_pause=True\n                        checkpoint('held_reconciliation')", "                        quarantine=read(ROOT/'quarantine.json').get('jobs',[])\n                        quarantine.append(row['job']);durable('quarantine.json',dict(jobs=quarantine))\n                        finish(row,dict(engineering_clean=False,reason='runner_receipt_missing_quarantined',automatic_retry=False))\n                        checkpoint('running')")
s=s.replace("    if not read(ROOT/'budget-migration.json').get('finalized'):raise RuntimeError('Waiting for parent campaign budget finalization')\n",'')
s=s.replace('total_trials=1,retry_batches=0,total_concurrency=1','total_trials=150,retry_batches=0,total_concurrency=6')
(ROOT/'campaign.py').write_text(s)
cfg=dict(schema_version=9,selection='seeded_uniform_50_of_89_seed_20261017',task_count=50,trial_count=150,concurrency=6,solver_seconds=2700,engineering_retry_batches=0,preflight_attempts_per_trial=1,retry_score_zero=False,retry_valid_budget_exhaustion=False)
(ROOT/'experiment.json').write_text(json.dumps(cfg,indent=2))
ex=(BASE/'experiment.py').read_text();a=ex.index('    expected = dict(');b=ex.index('    if config != expected',a)
ex=ex[:a]+'    expected = '+repr(cfg)+'\n'+ex[b:]
ex=ex.replace("'per_arm':1","'per_arm':2")
(ROOT/'experiment.py').write_text(ex)
with tarfile.open(ROOT/'upload.tar.gz','w:gz') as tar:
    for p in ROOT.iterdir():
        if p.suffix in ('.py','.json','.mjs') and p.name!='build_local.py':tar.add(p,arcname=p.name)
    for folder in ('src','tests'):
        for p in (PROJECTS/'kz-dsh'/folder).rglob('*'):
            if p.is_file():tar.add(p,arcname='latest-dsh/'+p.relative_to(PROJECTS/'kz-dsh').as_posix())
    native=PROJECTS/'kz-native-orthogonal-trigger-20261017/native'
    for p in native.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:tar.add(p,arcname='native/'+p.relative_to(native).as_posix())
print('Prepared independent campaign source bundle')
