"""Record Harbor ownership/exit outside Harbor; never retry a child process."""
import os
import subprocess
import sys
from pathlib import Path
from recovery import process_identity
from storage import atomic_json


def run(command, root, attempt, popen=subprocess.Popen):
    if not attempt or any(c not in '0123456789abcdef' for c in attempt):
        raise ValueError('Explicit attempt ID required')
    path=Path(root)/'attempts'/(attempt+'.json')
    if path.exists():raise RuntimeError('Attempt already has a runner receipt')
    receipt=dict(schema_version=1,attempt_id=attempt,state='admitted',runner=process_identity(os.getpid()))
    atomic_json(path,receipt)
    try:
        child=popen(command,stdin=subprocess.DEVNULL)
    except Exception as error:
        atomic_json(path,{**receipt,'state':'launch_failed','harbor_exit':127,'error_type':type(error).__name__})
        raise
    # If this write fails, keep waiting for the paid process; never kill or replay it.
    receipt.update(state='running',harbor=process_identity(child.pid))
    try:atomic_json(path,receipt)
    except OSError:pass
    code=child.wait()
    atomic_json(path,{**receipt,'state':'completed','harbor_exit':code})
    return code


if __name__=='__main__':
    raise SystemExit(run(sys.argv[1:],Path(__file__).resolve().parent,os.environ['PAIRED_ATTEMPT_ID']))
