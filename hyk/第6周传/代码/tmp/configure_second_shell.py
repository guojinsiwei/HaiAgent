"""Enable the prepared environment only for interactive shells in notebook two."""
from pathlib import Path
import platform
import shutil
import uuid

if platform.node()!='lizh639-8e64':
    raise SystemExit('Refusing to modify a different notebook shell')
path=Path('/root/.bashrc')
original=path.read_text() if path.exists() else ''
marker='# BestFGS notebook 2 interactive environment'
if marker not in original:
    if path.exists():
        shutil.copy2(path,path.with_name('.bashrc.before-bestfgs-'+uuid.uuid4().hex[:10]))
    path.write_text(original.rstrip()+'\n\n'+marker+'\n'
                    'if [[ $- == *i* ]] && [[ -f /mnt/lizh639/notebook-tools/activate_bestfgs_notebook.sh ]]; then\n'
                    '    source /mnt/lizh639/notebook-tools/activate_bestfgs_notebook.sh\n'
                    'fi\n')
print('Interactive shell now activates the shared bestfgs environment; no experiment auto-start')
