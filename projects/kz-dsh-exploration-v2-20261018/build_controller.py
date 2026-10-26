"""Adapt the previously validated LongCLI isolation controller for paired runs."""
from pathlib import Path
R=Path(__file__).parent
if (R/'runner.py').exists() or (R/'container-run.mjs').exists():
 raise SystemExit('Historical one-time generator: final controller contains reviewed fixes. Never overwrite it; edit final sources directly.')
s=Path('experiment_records/longcli-kz-dsh3-20261012/runner.py').read_text()
def swap(a,b):
 global s
 assert a in s,a[:80];s=s.replace(a,b)
swap('from common import ROOT, save, sha, import_tree, export_tree', '''from common import ROOT, save, sha, import_tree, export_tree
from spending import Ledger,server_for
GRADE_LOCK=threading.Lock()
TB=Path('/mnt/sdb/home/lizh639/tb2-three-arm50-20261017')''')
swap("route=lines(directory/'audit/request-route.jsonl')", "route=lines(directory/'audit/route.jsonl')")
swap('def trial(row,key):\n    job=\'kz--\'+row[\'task\'];directory=ROOT/\'jobs\'/job', "def trial(row,key,arm,ledger):\n    job=arm+'--'+row['task'];directory=ROOT/'jobs'/job")
swap('proxy=None;p=None;container_created=False;network_created=False', 'proxy=None;p=None;budget_server=None;container_created=False;network_created=False')
swap("source_version='KZ-DSH-0.2.4'", "source_version=arm,arm=arm")
swap('proxy=Proxy(gateway)', '''proxy=Proxy(gateway)
        budget_token=secrets.token_urlsafe(32)
        budget_server=server_for(ledger,budget_token,host=gateway,port=0)
        threading.Thread(target=budget_server.serve_forever,daemon=True).start()
        spending=dict(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=f'http://{gateway}:{budget_server.server_port}',
            CAMPAIGN_BUDGET_TOKEN=budget_token,CAMPAIGN_BUDGET_JOB=job,CAMPAIGN_BUDGET_ARM='kz')''')
swap("(ROOT/'runtime/kz','/opt/kz',True),\n            (ROOT/'runtime/node','/opt/node',True)", "(ROOT/'runtime'/arm,'/opt/kz',True),\n            (TB/'runtime/kz/node_modules','/opt/kz/node_modules',True),\n            (TB/'runtime/node','/opt/node',True)")
swap("(ROOT/'container_run.py','/opt/experiment/container_run.py',True)", "(ROOT/'container-run.mjs','/opt/experiment/container-run.mjs',True)")
swap("[row['image_id'],'python3','/opt/experiment/container_run.py']", "[row['image_id'],'/opt/node/bin/node','/opt/experiment/container-run.mjs']")
swap("{'key':key,'proxy':proxy.url}", "{'key':key,'proxy':proxy.url,'no_proxy':gateway+',localhost,127.0.0.1','spending':spending,'arm':'kz','instruction':row['instruction'],'attempt_id':job}")
swap('>7260','>2760')
swap("report=grade_source(summary,directory)", "with GRADE_LOCK:report=grade_source(summary,directory)")
swap('        if proxy:proxy.close()', '        if proxy:proxy.close()\n        if budget_server:budget_server.shutdown();budget_server.server_close()')
a=s.index('def validate():');s=s[:a]+'''def validate():
    ready=json.loads((ROOT/'ready.json').read_text());assert ready['passed']
    for name,value in ready['hashes'].items():assert sha(ROOT/name)==value,'Changed sealed deployment: '+name
    protocol=json.loads((ROOT/'protocol.json').read_text())
    assert len(protocol['tasks'])==6 and protocol['methods']==['baseline','candidate']
    return protocol

def campaign(key):
    protocol=validate();ledger=Ledger(ROOT/'spending.sqlite',json.loads((ROOT/'budget-profile.json').read_text()))
    assert ledger.status()['settled_microcny']==0,'Fresh campaign only; no silent replay'
    queue=[]
    for i,row in enumerate(protocol['tasks']):
        for arm in (['baseline','candidate'] if i%2==0 else ['candidate','baseline']):queue.append((row,arm))
    results=[];active={}
    with ThreadPoolExecutor(max_workers=2) as pool:
        while queue or active:
            for future in list(active):
                if future.done():
                    row,arm=active.pop(future)
                    try:results.append(future.result())
                    except Exception as exc:results.append(dict(task=row['task'],arm=arm,state='needs_attention',engineering_fault=type(exc).__name__))
            # Reserve a conservative workspace allowance before admitting any new task.
            # Never clean other containers or reclaim historical snapshots.
            while queue and len(active)<2 and shutil.disk_usage('/var/lib/docker').free>40*2**30 and shutil.disk_usage(ROOT).free>10*2**30:
                row,arm=queue.pop(0);active[pool.submit(trial,row,key,arm,ledger)]=(row,arm)
            snapshot=dict(state='running' if active else 'waiting_for_storage' if queue else 'complete',updated=time.time(),pid=os.getpid(),
                concurrency=len(active),completed=results,pending=[dict(task=r['task'],arm=a) for r,a in queue],
                active=[dict(task=r['task'],arm=a) for r,a in active.values()],budget=ledger.status())
            save(ROOT/'health.json',snapshot)
            if queue or active:time.sleep(5)
    snapshot['state']='complete_with_engineering_failures' if any(r['state']!='graded' for r in results) else 'complete'
    save(ROOT/'summary.json',snapshot);save(ROOT/'health.json',snapshot)

if __name__=='__main__':
    if '--supervise' in sys.argv:
        payload=json.loads(sys.stdin.readline(16384));campaign(payload.pop('key'))
    elif '--launch' in sys.argv:
        validate();bundle=json.loads(sys.stdin.readline(16384));key=bundle.get('key','')
        assert key and key.isascii() and not any(c.isspace() for c in key)
        with (ROOT/'launch-once.marker').open('x') as f:f.write('Six paired KZDSH tasks, independent 48 CNY planned within 96 CNY authorization; no automatic replay.\\n')
        with (ROOT/'supervisor.log').open('ab',buffering=0) as log:
            p=subprocess.Popen([sys.executable,__file__,'--supervise'],stdin=subprocess.PIPE,stdout=log,stderr=log,start_new_session=True)
            p.stdin.write((json.dumps({'key':key})+'\\n').encode());p.stdin.close()
        key='';bundle={};time.sleep(2)
        assert p.poll() is None,'Supervisor exited; inspect before retry'
        print(json.dumps(dict(started=True,pid=p.pid,campaign=ROOT.name,trials=12,concurrency=2,maximum_cny=48)))
    else:validate();print('READY; no model calls')
'''
s=s.replace('import secrets\n','import secrets\nimport shutil\n')
(R/'runner.py').write_text(s)
# Same bounded provider/accounting path as the existing campaign, isolated logs/ledger.
container=Path('projects/tb2-three-arm50-20261017/container-run.mjs').read_text()
container=container.replace("const logs='/logs/agent/live'", "const logs='/audit'")
container=container.replace("KZ_TASK_INSTRUCTION_PATH:'BENCHMARK_INSTRUCTION.md'", "KZ_TASK_INSTRUCTION_PATH:'INSTRUCTION.md'")
(R/'container-run.mjs').write_text(container)
(R/'spending.py').write_text(Path('projects/tb2-three-arm50-20261017/spending.py').read_text())
(R/'test_bounded_ledger.py').write_text(Path('projects/tb2-three-arm50-20261017/test_bounded_ledger.py').read_text())
print('Controller generated with shared bounded ledger, per-task isolation, two slots and serialized scoring')
