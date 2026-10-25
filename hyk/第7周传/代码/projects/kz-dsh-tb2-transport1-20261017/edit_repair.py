"""One-time construction of this isolated engineering repair release."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent
def edit(n,a,b):
 p=R/n;s=p.read_text();assert a in s,(n,a);p.write_text(s.replace(a,b),encoding='utf-8')
config=dict(schema_version=6,selection='tb2_paired_authorized_engineering_repair_seven',task_count=5,trial_count=7,concurrency=2,solver_seconds=2700,engineering_retry_batches=0,preflight_attempts_per_trial=1,retry_score_zero=False,retry_valid_budget_exhaustion=False)
(R/'experiment.json').write_text(json.dumps(config,indent=2))
edit('experiment.py',"schema_version=3, selection='tb2_official_sample_names_from_pinned_full_dataset', task_count=10,\n                    concurrency=1", "schema_version=6, selection='tb2_paired_authorized_engineering_repair_seven', task_count=5, trial_count=7,\n                    concurrency=2")
edit('experiment.py',"2*config['task_count']","config['trial_count']")
edit('experiment.py',"'per_arm':config['concurrency']","'per_arm':1")
edit('entry_harbor.py',"self.config.agent.import_path in ('agents:DSH','agents:PureDSH')", "(self.config.agent.import_path or self.config.agent.name) in ('agents:DSH','agents:PureDSH','agents:OfflineDSH','agents:OfflinePureDSH','agents:OfflineTimeout')")
edit('campaign.py','PORT=28615','PORT=28645')
edit('campaign.py','port=28616','port=28646')
edit('campaign.py',"total_trials=20,retry_batches=0,total_concurrency=1", "total_trials=7,retry_batches=0,total_concurrency=2")
edit('campaign.py',"if any(v['row']['arm']==row['arm'] for v in active.values()):continue", "if len(active)>=2:break\n                    if any(v['row']['arm']==row['arm'] for v in active.values()):continue")
# Count other known campaign reservations while admitting our own concurrent jobs.
edit('campaign.py',"    return (shutil.disk_usage('/var/lib/docker').free>=disk_need(task)+sum(disk_need(x['row']['task']) for x in active.values())", "    external=sum(len(read(p).get('active',[])) for p in ROOT.parent.glob('tb2-*/health.json') if p.parent!=ROOT)\n    return (shutil.disk_usage('/var/lib/docker').free>=disk_need(task)+sum(disk_need(x['row']['task']) for x in active.values())+external*30*1024**3")
edit('campaign.py',"from queue_policy import TERMINAL,initial_rows,append_retry_batch,candidates,finish,first_finished,summary", "from queue_policy import TERMINAL,initial_rows,append_retry_batch,candidates,finish,first_finished,summary")
edit('queue_policy.py',"    rows=[]\n", "    rows=[]\n")
s=(R/'queue_policy.py').read_text();start=s.index('def initial_rows(');end=s.index('def first_finished(')
s=s[:start]+'''AUTHORIZED=[('build-cython-ext','kz-dsh'),('qemu-alpine-ssh','dsh'),('qemu-alpine-ssh','kz-dsh'),('qemu-startup','kz-dsh'),('regex-log','kz-dsh'),('sqlite-with-gcov','dsh'),('sqlite-with-gcov','kz-dsh')]

def initial_rows(names, history):
    if set(names)!={t for t,a in AUTHORIZED}:raise ValueError('Unexpected repair selection')
    return [dict(task=t,arm=a,stage='first',job=f'repair1-{i+1:02d}-{a}-{t}',state='pending') for i,(t,a) in enumerate(AUTHORIZED)]

'''+s[end:]
start=s.index('def candidates(');end=s.index('def finish(')
s=s[:start]+'''def candidates(rows, active_arms):
    selected=[];busy=set(active_arms)
    for row in rows:
        if len(busy)>=2:break
        if row['state']=='pending' and row['arm'] not in busy:
            selected.append(row);busy.add(row['arm'])
    return selected

'''+s[end:];(R/'queue_policy.py').write_text(s)
# Old tests retain their generic 30-task fixtures through an explicitly injected queue.
edit('test_campaign.py',"self.budget_patch=patch.object(c,'BudgetService',FakeBudget);self.budget_patch.start();self.addCleanup(self.budget_patch.stop)", "self.budget_patch=patch.object(c,'BudgetService',FakeBudget);self.budget_patch.start();self.addCleanup(self.budget_patch.stop)\n        def fixture_rows(names,history):\n            return [dict(task=t,arm='kz-dsh',stage='first',job=f'first-{i+1:02d}-kz-dsh-{t}',state='pending') for i,t in enumerate(names)]\n        p=patch.object(c,'initial_rows',side_effect=fixture_rows);p.start();self.addCleanup(p.stop)")
edit('test_engineering.py',"fields['max_trials_with_retry'],20", "fields['max_trials_with_retry'],7")
# Supply official dependency archives exclusively to the verifier, after solver collection.
edit('lifecycle_guard.py',"        record(self,'verifying')", "        from verifier_setup import prepare_verifier\n        await prepare_verifier(a[0] if a else kw['verifier'])\n        record(self,'verifying')")
# Private files can be written after a best-effort early chown. Explicitly hand off
# the fixed log mount with root privileges at the collection boundary.
edit('lifecycle_guard.py',"            await self.agent_environment.prepare_logs_for_host()", "            await handoff_logs(self.agent_environment)")
edit('lifecycle_guard.py',"            await self.prepare_logs_for_host()", "            await handoff_logs(self)")
idx=(R/'lifecycle_guard.py').read_text().index('def install(')
s=(R/'lifecycle_guard.py').read_text();s=s[:idx]+'''async def handoff_logs(env):
    await env.prepare_logs_for_host()
    # Fixed trusted bind mount only; find -P never follows solver symlinks.
    command=f"test ! -L /logs/agent && find -P /logs/agent -xdev -type d -exec chown {os.getuid()}:{os.getgid()} {{}} + -exec chmod u+rwx {{}} + && find -P /logs/agent -xdev -type f -exec chown {os.getuid()}:{os.getgid()} {{}} + -exec chmod u+r {{}} +"
    result=await env._run_docker_compose_command(['exec','-T','-u','root','main','sh','-c',command],check=False,timeout_sec=60)
    if result.return_code:raise CollectionFailure('Explicit private log handoff failed')

'''+s[idx:];(R/'lifecycle_guard.py').write_text(s)
# Test doubles use an explicit successful handoff, while real acceptance checks chmod600.
edit('accept_harbor.py',"task='regex-log'", "task=sys.argv[3] if len(sys.argv)>3 else 'build-cython-ext'")
edit('seal.py',"engineering_revision='engineering-1'", "engineering_revision='paired-repair-2'")
edit('seal.py',"names += [ROOT/'baseline-lifecycle-result.json']", "names += [ROOT/n for n in ('baseline-lifecycle-result.json','verifier-deps.tar.gz','verifier-deps-provenance.json','parent-results.json','budget-migration.json','repair-queue.json','timeout-lifecycle-result.json')]")
edit('seal.py',"    baseline=json.loads", "    timeout=json.loads((ROOT/'timeout-lifecycle-result.json').read_text())\n    require(timeout.get('passed') and timeout.get('source_hashes')==report['source_hashes'],'Forced deadline acceptance required')\n    baseline=json.loads")
print('repair edits applied')
