import pathlib,subprocess,json,os
r=pathlib.Path(__file__).resolve().parent
node=str(r.parent.parent/'tb2-three-arm50-20261017/runtime/node/bin/node')
env={**os.environ,'PATH':str(pathlib.Path(node).parent)+':'+os.environ['PATH']}
results=[]
checks=[('guard',['python3','-m','unittest','-v','test_guard.py']),('repairs',[node,'--test','test_repairs.mjs'])]
for arm in ['hld','kzdsh-new']:
    tests=['repair4-review.test.mjs','subgoal-controller-repair5.test.mjs','subgoal-edge-repair5.test.mjs','shell-receipts-repair5.test.mjs','full.test.mjs','subgoal-integration-repair5.test.mjs']
    if arm=='hld':tests+=['semantic-planner.test.mjs','semantic-integration.test.mjs']
    checks.append((arm,[node,'--test',*[str(r/'runtime'/arm/'tests'/t) for t in tests]]))
for name,cmd in checks:
    p=subprocess.run(cmd,cwd=r,capture_output=True,text=True,timeout=240,env=env)
    (r/(name+'-tests.log')).write_text(p.stdout+p.stderr)
    results.append({'name':name,'returncode':p.returncode,'summary':(p.stdout+p.stderr)[-1800:]})
    print(name,p.returncode,flush=True)
(r/'offline-tests.json').write_text(json.dumps({'passed':all(x['returncode']==0 for x in results),'results':results,'paid_calls':0},indent=2))
raise SystemExit(0 if all(x['returncode']==0 for x in results) else 1)
