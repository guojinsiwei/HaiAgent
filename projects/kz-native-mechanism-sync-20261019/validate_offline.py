"""Run local Linux behavioral suites with machine-readable failure accounting."""
import sys,unittest,json,os
from pathlib import Path
root=Path(__file__).resolve().parent
native=root/'native'
sys.path[:0]=[str(native),str(native/'legacy/sources/bestfgs-project/src'),str(native/'legacy/compatibility/src')]
import solve
suite=unittest.TestSuite()
loader=unittest.TestLoader()
for module in ['test_exploration_trigger','test_exploration_learning','test_mechanism_parity','test_native_repair','test_provider_policy','test_bridge']:
    suite.addTests(loader.loadTestsFromName(module))
sys.path.insert(0,str(native/'legacy/sources/bestfgs-project/tests'))
for module in ['test_lean']:
    suite.addTests(loader.loadTestsFromName(module))
(root/'audit').mkdir(exist_ok=True)
with (root/'audit/offline-tests.log').open('w') as stream:
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
summary=dict(tests=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
             failures=[{'test':str(t),'traceback':s} for t,s in result.failures],errors=[{'test':str(t),'traceback':s} for t,s in result.errors],
             skipped=[{'test':str(t),'reason':s} for t,s in result.skipped],platform=sys.platform,python=sys.version,model_calls=0)
(root/'audit/offline-summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
sys.exit(not result.wasSuccessful())
