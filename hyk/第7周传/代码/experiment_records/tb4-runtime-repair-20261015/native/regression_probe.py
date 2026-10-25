import json,sys,unittest
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path[:0]=[str(root),str(root/'sources/bestfgs-project/src'),str(root/'compatibility/src')]
suite=unittest.defaultTestLoader.discover(str(root/'sources/bestfgs-project/tests'),pattern='test_lean.py')
result=unittest.TextTestRunner(verbosity=1).run(suite)
print(json.dumps(dict(tests=result.testsRun,failures=sorted(t.id() for t,_ in result.failures),errors=sorted(t.id() for t,_ in result.errors))))
