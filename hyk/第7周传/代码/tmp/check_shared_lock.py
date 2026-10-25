import fcntl
from pathlib import Path
import sys
import time

path = Path('/mnt/lizh639/notebook-checks/paired-cross-host-lock')
path.parent.mkdir(parents=True, exist_ok=True)
with path.open('a+b') as stream:
    if sys.argv[1] == 'hold':
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print('LOCK_HELD', flush=True)
        time.sleep(20)
    else:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('CROSS_HOST_EXCLUSION_OK', flush=True)
        else:
            print('ERROR_NO_CROSS_HOST_EXCLUSION', flush=True)
            sys.exit(2)
