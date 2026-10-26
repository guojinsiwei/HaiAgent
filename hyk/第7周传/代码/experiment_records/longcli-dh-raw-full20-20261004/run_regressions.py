"""Run frozen DH regression tests without a provider or API credential."""
import json
import unittest
from common import ROOT,save
from environment import NativeEnvironment

suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
result=unittest.TextTestRunner(verbosity=1).run(suite)
report=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,failures=len(result.failures),
    errors=len(result.errors),skipped=len(result.skipped),model_api_calls=0)
save(ROOT/'offline-acceptance.json',report)
print(json.dumps(report))
raise SystemExit(0 if report['passed'] and report['tests_run']==128 else 1)
