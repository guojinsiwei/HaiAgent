"""Bounded offline release checks, independent subprocesses and durable logs."""
import hashlib
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
    'repairs': ['discover', '-s', 'tests'],
    'classification': ['discover', '-s', 'integration', '-p', 'test_outcomes.py'],
    'supervision': ['discover', '-s', 'integration', '-p', 'test_supervisor.py'],
}
results = []
previous = ROOT/'evidence/validation.json'
passed = {r['group']:r for r in json.loads(previous.read_text()).get('groups', [])
          if r['exit_code'] == 0 and r['tests'] > 0} if '--resume' in sys.argv and previous.exists() else {}
for name, args in groups.items():
    if name in passed:
        results.append(passed[name])
        print(json.dumps(dict(passed[name], reused_verified_result=True)), flush=True)
        continue
    run = subprocess.run([sys.executable, '-B', '-m', 'unittest', *args], cwd=ROOT, env=env,
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    (ROOT/'evidence'/('regression-'+name+'.log')).write_text(run.stdout)
    count = re.search(r'Ran (\d+) tests?', run.stdout)
    result = dict(group=name, exit_code=run.returncode, tests=int(count[1]) if count else 0)
    results.append(result)
    print(json.dumps(result), flush=True)
    if run.returncode:
        print(run.stdout[-6000:], flush=True)
        break
success = len(results) == len(groups) and all(r['exit_code'] == 0 and r['tests'] > 0 for r in results)
if success:
    replay = subprocess.run([sys.executable, '-B', 'replay_classification.py'], cwd=ROOT, env=env,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    (ROOT/'evidence/replay.log').write_text(replay.stdout)
    success = replay.returncode == 0
summary = dict(success=success, groups=results, total_tests=sum(r['tests'] for r in results), model_calls=0)
(ROOT/'evidence/validation.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary), flush=True)
sys.exit(0 if success else 1)
