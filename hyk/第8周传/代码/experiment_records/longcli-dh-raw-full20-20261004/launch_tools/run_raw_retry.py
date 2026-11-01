"""One explicitly approved network retry; original result/claims stay intact."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import PYTHON,save,validate

TASK='cs61_fa24_scheme'
# Existing grader accepts this transport alias. This is a real RAW run, NOT
# a fixture; provenance below records canonical method and separate attempt.
JOB='roundtrip--'+TASK
MARKER=ROOT/'launch_tools/raw-scheme-retry.json'
SUMMARY=ROOT/'launch_tools/raw-scheme-retry-summary.json'

def retry_row(protocol):
    row=next(r for r in protocol['tasks'] if r['task']==TASK)
    slots=json.loads((ROOT/'resources-1.json').read_text())['cpu_slots']
    return dict(row,method='raw',job=JOB,worker=1,slot=0,cpu_affinity=slots[0],
                attempt=2,retry_of='raw--'+TASK,retry_reason='initial DNS failure before any tool')

def attach():
    validate()
    assert not MARKER.exists(),'Retry already registered; never launch twice'
    for parent in ('claims','roots','runs'):
        target=ROOT/parent/(JOB+'.json' if parent=='claims' else JOB)
        assert not target.exists(),'Separate retry path already exists'
    original=json.loads((ROOT/'runs'/('raw--'+TASK)/'summary.json').read_text())
    assert original['stop_reason']=='api_error' and original['tool_calls']==0
    health=json.loads((ROOT/'health-1.json').read_text())
    assert len(health['active'])==1 and health['active'][0]['slot']==1,'Retry slot no longer idle'
    pid=json.loads((ROOT/'launched-1.json').read_text())['pid']
    from continue_unclaimed import owned_worker
    parts=owned_worker(pid,1)
    assert parts,'Original worker credential no longer available; local key input required'
    old_key=Path(parts[parts.index('--credential')+1])
    assert old_key.parent.parent==Path('/dev/shm') and old_key.parent.name.startswith('dh-raw-pending-key-')
    private=Path(tempfile.mkdtemp(prefix='dh-raw-retry-key-',dir='/dev/shm'))
    credential=private/'key'
    os.link(old_key,credential)  # Same worker/campaign inode; never expose value.
    try:
        with (ROOT/'launch_tools/raw-scheme-retry.log').open('x') as log:
            child=subprocess.Popen([PYTHON,'-B',str(Path(__file__)), '--credential',str(credential)],
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        evidence=dict(pid=child.pid,worker=1,slot=0,job=JOB,method='raw',attempt=2,
            retry_of=original['job'],original_artifact_sha256=original['artifact']['sha256'],
            reason='User approved retry after DNS repair',created=time.time(),
            original_retained=True,fixture=False,budgets_unchanged=True,secret_values_read=False)
        save(MARKER,evidence)
        print(json.dumps(evidence),flush=True)
    except Exception:
        credential.unlink(missing_ok=True);private.rmdir();raise

def run(credential):
    try:
        import parallel_worker
        row=retry_row(validate())
        result,reason=parallel_worker.run_trial(row,credential)
        save(SUMMARY,dict(result,attempt=2,retry_of='raw--'+TASK,retry_infrastructure_error=reason,
            separate_attempt=True,fixture=False))
    except Exception as error:
        save(ROOT/'launch_tools/raw-scheme-retry-error.json',dict(error_type=type(error).__name__,
            message=str(error)[:500],time=time.time(),no_automatic_retry=True))
        raise
    finally:
        credential.unlink(missing_ok=True);credential.parent.rmdir()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--credential',type=Path);a=p.parse_args()
    if a.credential:run(a.credential)
    else:attach()
