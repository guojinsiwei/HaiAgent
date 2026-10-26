"""One authorized campaign launch after all offline acceptance gates pass."""
from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parent


def main():
    for name in ['preflight-result.json','integration-preflight.json']:
        d=json.loads((R/name).read_text());assert d['passed'] and d['paid_calls']==0
    assert not (R/'launch-once.marker').exists()
    manifest=json.loads((R/'manifest.json').read_text())
    for row in manifest['selected']:
        assert hashlib.sha256((R/'data'/row['game']).read_bytes()).hexdigest()==row['sha256']
    files=[p for p in R.iterdir() if p.suffix in ('.py','.mjs')]
    files += [R/n for n in ['protocol.json','manifest.json','budget-profile.json','image.json','official-source.json']]
    for part in ['kz/src','kz/config','kz/.runtime','recuris-dsh/src','dsh-baselines/src']:
        files += [p for p in (R/'runtime'/part).rglob('*') if p.is_file() and p.suffix in ('.mjs','.py','.yml')]
    files += list((R/'runtime/kz').glob('*.mjs'))
    files += [R/'runtime/kz/route.patch.yml',R/'runtime/kz/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js',R/'runtime/node/bin/node']
    locked={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (R/'source-lock.json').write_text(json.dumps(locked,indent=2))
    env={k:v for k,v in os.environ.items() if not any(x in k for x in ('API_KEY','AUTH_TOKEN','CAMPAIGN_BUDGET'))}
    env.update(PYTHONPATH=str(R),PYTHONDONTWRITEBYTECODE='1')
    with (R/'supervisor.log').open('x') as log:
        p=subprocess.Popen(['python3',str(R/'runner.py')],cwd=R,env=env,stdin=subprocess.DEVNULL,
             stdout=log,stderr=log,start_new_session=True)
    time.sleep(3);assert p.poll() is None,'Supervisor exited; inspect before retry'
    result=dict(pid=p.pid,trials=160,per_trial_cny=7,total_limit_cny=1120,concurrency_cap=12,
                existing_experiments_reserved=True,paid_grading_calls=0,gpt_automation=False)
    (R/'launch-receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()
