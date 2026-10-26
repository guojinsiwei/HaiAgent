"""Reproduce the official copy-before-EXIT-trap behavior in a real container."""
from pathlib import Path
import json
import runner
R=Path(__file__).resolve().parent
fixture=R/'audit/verifier-directory-repair/fixture'
(fixture/'tests').mkdir(parents=True,exist_ok=True)
(fixture/'tests/config.json').write_text(json.dumps({'fail_to_pass':['directory-regression'],'pass_to_pass':[]}))
(fixture/'tests/test.sh').write_text('''#!/bin/bash
set -e
trap 'mkdir -p /logs/verifier; echo 1 > /logs/verifier/reward.txt' EXIT
echo '{"tests":[{"name":"directory-regression","status":"PASSED"}]}' > /tmp/output.json
cp /tmp/output.json /logs/verifier/output.json 2>/dev/null || true
''')
runner.task_path=lambda task:fixture
runner.cwd_of=lambda name:'/app'
result=runner.grade({'image_id':'sha256:f986820b00c74ce75db7288719d364df313fde7c7917bea6eb6352a08431a89f'},fixture/'actual')
assert result['engineering_clean'] and result['reward']==1 and result['required_passed']==1,result
print(json.dumps(result))
