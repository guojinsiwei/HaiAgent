"""One-shot trial child; reconnecting supervision never restarts an attempted job."""
import fcntl
import json
import os
from pathlib import Path
import sys
import time
from control import HERE,execute,validate
from prepare import write
from outcomes import classify
from supervisor import identity

def trial(name):
    directory=HERE/'ledger'/name
    with (directory/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (directory/'started.json').exists():raise RuntimeError('Never replay an attempted trial')
        validate()
        spec=json.loads((directory/'intent.json').read_text())
        if name!=spec['method']+'-'+spec['task']['task']:raise RuntimeError('Ledger identity mismatch')
        write(directory/'started.json',dict(pid=os.getpid(),identity=identity(os.getpid()),time=time.time()))
        try:
            result=execute(spec['task'],spec['method'])
            events=[json.loads(s) for s in (Path(result['report']).parent/'agent/audit.jsonl').read_text().splitlines()]
            result['classification']=classify(dict(result,method='raw'),events)
        except Exception as error:
            result=dict(task=spec['task']['task'],method=spec['method'],infrastructure_error=type(error).__name__,
                classification=dict(infrastructure_ok=False,reasons=['trial_worker_exception:'+type(error).__name__]))
        write(directory/'result.json',result)

if __name__=='__main__':
    if sys.argv[1]!='trial':raise ValueError('Only supervised one-shot trials are supported')
    trial(sys.argv[2])
