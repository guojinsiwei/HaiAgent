"""New, isolated KZ 0.3.0 deployment; never mutate the parent campaign."""
import hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014')
WATCH=Path('/var/tmp/lizh639-tb4-server-watchdog-20261014')
def replace_once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)
def main():
    assert not (ROOT/'runtime').exists(),'Refuse to overwrite prepared candidate'
    runtime=ROOT/'runtime';runtime.mkdir()
    with tarfile.open(BASE/'runtime-final.tar.gz') as archive:archive.extractall(runtime,filter='data')
    kz=runtime/'kz'
    with tarfile.open(ROOT/'source.tar.gz') as archive:archive.extractall(kz,filter='data')
    assert json.loads((kz/'package.json').read_text())['version']=='0.3.0'
    shutil.copytree(BASE/'official',ROOT/'official')
    shutil.copy2(BASE/'official-hashes.json',ROOT/'official-hashes.json')
    for name,h in json.loads((ROOT/'official-hashes.json').read_text()).items():
        assert hashlib.sha256((ROOT/'official'/name).read_bytes()).hexdigest()==h,name
    tasks=json.loads((BASE/'tasks.json').read_text());tasks['tasks']=tasks['tasks'][:10]
    tasks['selection']='First 10 in the previously frozen 30-task order; no score-based reselection'
    (ROOT/'tasks.json').write_text(json.dumps(tasks,indent=2))
    for name in ('harbor_pair.py','unlimited_harbor.py','offline_accept.py','container-run.mjs','route.patch.yml','route-audit.mjs','shared-budget.mjs','boot-guard.mjs','test_scheduler.py','test_supervisor_loop.py'):
        shutil.copy2(BASE/name,ROOT/name)
    proxy=replace_once((BASE/'network_proxy.py').read_text(),"HOST,PORT='10.123.0.1',28479","HOST,PORT='10.123.0.1',28481")
    (ROOT/'network_proxy.py').write_text(proxy)
    runner=(BASE/'runner.py').read_text()
    runner=replace_once(runner,'TOTAL_CAP=4','TOTAL_CAP=2')
    runner=replace_once(runner,"for arm in (['kz','dsh'] if index%2==0 else ['dsh','kz']):","for arm in ['kz']:")
    runner=replace_once(runner,"if self.pause_reason or len(active)>=TOTAL_CAP:return None","if self.pause_reason or len(active)>=TOTAL_CAP:return None\n        first=self.rows[0]\n        if first['state']!='pending' and not (first.get('valid_solver_completion') and first.get('requests',0)>0 and first.get('tools',0)>0):return None")
    runner=replace_once(runner,'def observe_global(self,rows):',"def observe_global(self,rows):\n        first=self.rows[0]\n        if first['state'] in ('engineering_failure','blocked_environment','launch_error') or first['state']=='graded' and not (first.get('valid_solver_completion') and first.get('requests',0)>0 and first.get('tools',0)>0):\n            self.pause_reason='pilot_engineering_acceptance_failed';return")
    # A pending pilot must be the only paid admission, even if other preflights finish first.
    runner=replace_once(runner,"if row['state']=='pending' and self.tasks[row['task']]['state']=='ready' and counts[row['arm']]<ARM_CAP:","if row['state']=='pending' and (row is first or first.get('valid_solver_completion')) and self.tasks[row['task']]['state']=='ready' and counts[row['arm']]<ARM_CAP:")
    runner=replace_once(runner,'planned=60','planned=10')
    runner=replace_once(runner,'return ready',"check=subprocess.run(['systemctl','--user','is-active','--quiet','kz-ec10-watchdog.service']);assert check.returncode==0,'Scoped watchdog is not running'\n    return ready")
    (ROOT/'runner.py').write_text(runner)
    watchdog=(WATCH/'watchdog.py').read_text()
    start=watchdog.index('CAMPAIGNS=');end=watchdog.index('\n',start)
    watchdog=watchdog[:start]+'CAMPAIGNS=[ROOT]'+watchdog[end:]
    # Legacy KZ processes are not part of this candidate's scope.
    begin=watchdog.index("    if job.startswith('legacy-kz-')")
    end=watchdog.index('    # JS supplied',begin)
    watchdog=watchdog[:begin]+watchdog[end:]
    (ROOT/'watchdog.py').write_text(watchdog)
    shutil.copy2(WATCH/'container_guard.mjs',ROOT/'container_guard.mjs')
    for name in ('container-run.mjs','route.patch.yml','route-audit.mjs','shared-budget.mjs','boot-guard.mjs'):shutil.copy2(ROOT/name,kz/name)
    overlay=(kz/'.runtime/kz.patch.yml').read_text()
    assert 'budgetDisabled: true' in overlay and 'shellReceipts: true' in overlay
    overlay=replace_once(overlay,'        budgetDisabled: true','        budgetDisabled: true\n        serverWallSeconds: 10800\n        artifactRoots: ["/results"]')
    (kz/'.runtime/kz.patch.yml').write_text(overlay)
    protocol=json.loads((BASE/'protocol.json').read_text())
    protocol.update(arms=['KZ 0.3.0 on DSH 0.2.0-rc.2'],paired_tasks=None,total_trials=10,parent_campaign=str(BASE),status='offline_acceptance_pending',results_reused=False)
    protocol['budget']['server_solver_seconds']=10800
    protocol['concurrency']={'total':2,'per_arm':2,'pilot':1,'unpaid_preflights':2}
    protocol['algorithm_role_limits']='Evidence-control-1; no two-review auto-delivery; shared unlimited accounting and existing role cooldowns; explicit 3-hour server deadline'
    protocol['tasks_sha256']=hashlib.sha256((ROOT/'tasks.json').read_bytes()).hexdigest()
    protocol['acceptance']='Offline actual DSH + Linux tests; first paid task is the pilot and counts within the 10; remaining nine only after pilot engineering completion, not score threshold'
    (ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    files=['node','kz/node_modules','kz/src','kz/config','kz/package.json','kz/package-lock.json']
    files+=['kz/'+n for n in ('shared-budget.mjs','route.patch.yml','route-audit.mjs','boot-guard.mjs','container-run.mjs','.runtime/kz.patch.yml','.runtime/transport.patch.yml')]
    subprocess.run(['tar','-czf',str(ROOT/'runtime-final.tar.gz'),'-C',str(runtime),*files],check=True)
    (ROOT/'ready.json').write_text(json.dumps({'passed':False,'reason':'Target acceptance pending'}))
    print(json.dumps({'prepared':True,'tasks':[t['name'] for t in tasks['tasks']],'paid_calls':0}))
if __name__=='__main__':main()
