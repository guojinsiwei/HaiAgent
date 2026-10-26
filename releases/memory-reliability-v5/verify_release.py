"""Independent offline regression groups, with durable results and no model API."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join(str(ROOT/p) for p in
    ('sources', 'sources/bestfgs-project', 'sources/bestfgs-project/src', 'sources/hai-project/src', 'integration')))
groups = {
    'hai': ['discover', '-s', 'sources/hai-project/tests'],
    'lean': ['discover', '-s', 'sources/bestfgs-project/tests', '-p', 'test_lean*.py'],
    'views': ['discover', '-s', 'sources/bestfgs-project/tests', '-p', 'test_prompt_views.py'],
    'transport': ['discover', '-s', 'sources/bestfgs-project/tests', '-p', 'test_retrac_adapter.py'],
    'repairs_and_semantic': ['discover', '-s', 'tests'],
    'classification': ['discover', '-s', 'integration', '-p', 'test_outcomes.py'],
    'supervision': ['discover', '-s', 'integration', '-p', 'test_supervisor.py'],
}
results=[]
(ROOT/'evidence').mkdir(exist_ok=True)
for name,args in groups.items():
    run=subprocess.run([sys.executable,'-B','-m','unittest',*args],cwd=ROOT,env=env,
                       text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (ROOT/'evidence'/('regression-'+name+'.log')).write_text(run.stdout,encoding='utf-8')
    match=re.search(r'Ran (\d+) tests?',run.stdout)
    row=dict(group=name,exit_code=run.returncode,tests=int(match[1]) if match else 0)
    results.append(row); print(json.dumps(row),flush=True)
    if run.returncode: print(run.stdout[-8000:],flush=True)
summary=dict(success=all(r['exit_code']==0 and r['tests']>0 for r in results),groups=results,
             total_tests=sum(r['tests'] for r in results),model_calls=0)
(ROOT/'evidence/validation.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary),flush=True)
sys.exit(0 if summary['success'] else 1)
