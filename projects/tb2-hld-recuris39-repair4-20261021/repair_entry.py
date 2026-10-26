import runpy
from pathlib import Path
from repair_hooks import install

install()
runpy.run_path(str(Path(__file__).with_name('entry_harbor.py')), run_name='__main__')
