"""Hidden stdin credential; detached guard; exclusive launch and no task replay."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
from supervisor import Supervisor, VERSION, identity, read, write


def main():
    root, kind = Path(sys.argv[1]).resolve(), sys.argv[2]
    with (root/'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manager = Supervisor(root, kind)
        rows, active, blockers = manager.collect()
        if blockers: raise RuntimeError('Unresolved ledger blockers')
        if len(manager.prior)+len(rows) == manager.total:
            print(json.dumps({'launched': False, 'state': 'already_completed', 'new_model_calls': 0}))
            return
        started = read(root/'guard-started-v2.json')
        if started and identity(started['pid']) == started['identity']:
            print(json.dumps({'launched': True, 'state': 'already_running', 'new_model_calls': 0}))
            return
        # Both locks must be free: never launch a guard alongside an old worker.
        with (root/'guard.lock').open('a') as g, (root/'worker.lock').open('a') as w:
            fcntl.flock(g, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(w, fcntl.LOCK_EX | fcntl.LOCK_NB)
        key = sys.stdin.readline().strip()
        if not key or any(c.isspace() for c in key): raise RuntimeError('Invalid credential input')
        from haiagent.model import NoRedirect
        request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization':'Bearer '+key})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            catalog = json.load(response)
        if 'deepseek-flash' not in {m.get('id') for m in catalog.get('data', [])}:
            raise RuntimeError('Frozen model unavailable')
        script = Path(__file__).with_name('supervisor.py')
        launched_at=time.time()
        with (root/'supervisor-v2.log').open('a') as log:
            child = subprocess.Popen([sys.executable, '-B', str(script), 'guard', str(root), kind, '--key-stdin'],
                cwd=root, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            child.stdin.write((key+'\n').encode())
            child.stdin.close()
        key = None
        write(root/'guard-started-v2.json', {'pid':child.pid,'identity':identity(child.pid),'time':time.time()})
        for _ in range(90):
            state = read(root/'health.json', {})
            if (state.get('supervision_version') == VERSION and state.get('updated',0)>=launched_at
                    and state.get('stage')==manager.stage):
                print(json.dumps({'launched': True, 'state': state['state'], 'completed': state['completed'],
                                  'pending':state['pending'], 'active_count':len(state['active'])}))
                return
            if child.poll() is not None: raise RuntimeError('Guard exited; inspect supervisor-v2.log')
            time.sleep(1)
        raise RuntimeError('Launch unconfirmed; inspect before retrying')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'launched': False, 'error_type':type(error).__name__,
                          'message':'Launch not confirmed; inspect status. No credentials logged.'}))
        sys.exit(2)
