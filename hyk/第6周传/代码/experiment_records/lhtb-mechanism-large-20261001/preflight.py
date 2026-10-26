"""Exercise all five adapters and seal inputs after exact group regressions."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from control import HERE,PYTHON,environment,execute,source_hashes,group_options
from prepare import write

def main():
    if (HERE/'ready.json').exists():raise RuntimeError('Never reseal ready inputs')
    env=environment('A1')
    commands=[('deployment-regression',['-m','unittest','test_deployment','test_harness_patch']),
              ('lean-regression',['-m','unittest','discover','-s','arms/common/bestfgs-project/tests','-p','test_lean*.py']),
              ('route-regression',['-m','unittest','discover','-s','tests','-p','test_route_selection_v7.py'])]
    for name,args in commands:
        with (HERE/(name+'.log')).open('w') as stream:
            subprocess.run([PYTHON,'-B',*args],cwd=HERE,env=env,stdout=stream,stderr=subprocess.STDOUT,
                           check=True,timeout=240)
    fixtures={}
    task=json.loads((HERE/'manifest.json').read_text())['tasks'][0]
    for group in 'ABCDE':
        fixtures[group]=execute(task,group+'1',True)
    hashes=source_hashes()
    write(HERE/'ready.json',dict(ready=True,source_hashes=hashes,fixture_audits=fixtures,
        protocol_sha256=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        disk_reserve_gib=120,total_trials=120,pilot_trials=10,sealed_at=time.time(),model_calls=0,
        group_options={g:group_options(g) for g in 'ABCDE'}))
    print(json.dumps(dict(ready=True,pilot_trials=10,screen_trials=120,fixtures=5,model_calls=0)))

if __name__=='__main__':main()
