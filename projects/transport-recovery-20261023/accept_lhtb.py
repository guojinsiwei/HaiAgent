from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,subprocess,os,time
R=Path(__file__).resolve().parent;O=R/'lhtb'
rows=json.loads((O/'recovery-rows.json').read_text())
tests=[r for r in rows if r['restore_progress']]+[next(r for r in rows if r['task']=='nbody-accel-iterative' and r['arm']=='hld')]
if os.environ.get('ACCEPTANCE_JOBS'):tests=[r for r in tests if r['job'] in os.environ['ACCEPTANCE_JOBS'].split(',')]
def run(row):
    name=os.environ.get('ACCEPTANCE_PREFIX','accept-')+row['job'];cfg=dict(row,job=name)
    env=dict(os.environ,PYTHONPATH=str(O)+':'+str(O/'vendor-src'),ENTRY_ACCEPTANCE='1',PYTHONDONTWRITEBYTECODE='1')
    if row['restore_progress']:env['RECOVERY_ACCEPTANCE_JOB']=row['job']
    code="import campaign,json;row=json.loads("+repr(json.dumps(cfg))+");r=campaign.run_trial(row,True);campaign.save(campaign.ROOT/('acceptance-'+row['job']+'.json'),r);print(json.dumps(r))"
    with (O/(name+'.log')).open('x') as log:
        p=subprocess.run([str(O/'venv/bin/python'),'-c',code],cwd=O,env=env,stdout=log,stderr=log,timeout=14400)
    path=O/('acceptance-'+name+'.json')
    result=json.loads(path.read_text()) if path.exists() else {}
    report=dict(job=row['job'],exit=p.returncode,passed=p.returncode==0 and result.get('engineering_clean',False),
        old_reward=row.get('result',{}).get('reward'),restored_reward=result.get('reward'),result=result)
    (O/('validation-'+name+'.json')).write_text(json.dumps(report,indent=2))
    return report
with ThreadPoolExecutor(max_workers=6) as pool:
    results=list(pool.map(run,tests))
out=dict(passed=all(r['passed'] for r in results),model_calls=0,finished=time.time(),results=results)
(O/'stability-acceptance.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
