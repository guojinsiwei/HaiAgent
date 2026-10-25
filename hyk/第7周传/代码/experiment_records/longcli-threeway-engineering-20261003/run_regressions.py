"""Required tests for deployed runtimes; keep separate legacy-suite evidence."""
import json
import os
import re
import subprocess
from common import ROOT,PYTHON,save,sha

def main():
    results=[]
    for method in ('bestfgs-v6.1','orthogonal-v8','raw'):
        arm=ROOT/'arms'/('v8' if method=='orthogonal-v8' else 'v6')
        env=dict(os.environ,LONGCLI_METHOD=method,PYTHONDONTWRITEBYTECODE='1',
            PYTHONPATH=os.pathsep.join(map(str,[arm/'bestfgs-project/src',arm/'hai-project/src',
                arm/'bestfgs-project/tests',ROOT/'tests-v8',ROOT])))
        commands=[('shared',[PYTHON,'-B','-m','unittest','test_shared_wire','test_deployment','test_relay'])]
        if method=='bestfgs-v6.1':
            commands += [('lean',[PYTHON,'-B','-m','unittest','discover','-s',str(arm/'bestfgs-project/tests'),'-p','test_lean.py'])]
        if method=='orthogonal-v8':
            commands += [('current-features',[PYTHON,'-B','-m','unittest','test_memory_injection',
                'test_memory_reliability','test_command_identity','test_engineering_repair',
                'test_contrastive_exploration','test_conversation','test_terminal_and_handover'])]
        if method!='raw':
            commands += [('hai',[PYTHON,'-B','-m','unittest','discover','-s',str(arm/'hai-project/tests')])]
        for kind,argv in commands:
            path=ROOT/f'operational-v3-{method}-{kind}.log'
            with path.open('x') as log:
                p=subprocess.run(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
            content=path.read_text(errors='replace');count=re.search(r'Ran (\d+) tests?',content)
            results.append(dict(method=method,kind=kind,returncode=p.returncode,
                tests=int(count[1]) if count else None,log_sha256=sha(path)))
            print(json.dumps(results[-1]),flush=True)
    save(ROOT/'operational-regression.json',dict(passed=all(r['returncode']==0 for r in results),results=results,
        model_calls=0,scope='Shared wire/relay/admission plus deployed lean and RAW runtimes; legacy full-suite report retained separately'))

if __name__=='__main__':main()
