import tempfile, runpy, sys
from pathlib import Path
base=Path.cwd(); temp=base/'experiment_records/tb2-orthogonal-trigger-audit-20261017/test-tmp';temp.mkdir(exist_ok=True)
tempfile.tempdir=str(temp)
p=base/sys.argv[1]/'native';sys.argv=[str(p/'regression_probe.py'),str(p/'legacy')]
runpy.run_path(sys.argv[0],run_name='__main__')
