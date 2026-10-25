"""Single locked worker, bounded Raw runs, audit-preserving export; no auto reruns."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile
import threading
import time
from runner import HERE, run_one
from haiagent.storage import atomic_json

def validate():
    ready = json.loads((HERE/'ready.json').read_text())
    assert ready['ready']
    for name, expected in ready['hashes'].items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest() == expected, name
    return json.loads((HERE/'protocol.json').read_text())

def export(task_id):
    root = HERE/'roots'/task_id/'app'
    assert root.is_dir() and not root.is_symlink()
    files = []
    size = 0
    # Fail closed on links/devices; do not follow model-produced paths on the host.
    for parent, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            p = Path(parent)/name
            s = p.lstat()
            if stat.S_ISLNK(s.st_mode) or not (stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)):
                raise RuntimeError('Unsafe artifact entry; preserved for manual inspection')
            size += s.st_size if stat.S_ISREG(s.st_mode) else 0
            files.append(p)
            if len(files) > 30000 or size > 512*2**20:
                raise RuntimeError('Artifact export limit exceeded; preserved for manual inspection')
    dest = HERE/'artifacts'
    dest.mkdir(exist_ok=True)
    path = dest/(task_id+'.tar.gz')
    with tarfile.open(path, 'x:gz', dereference=False) as archive:
        for p in sorted(files):
            archive.add(p, arcname=str(p.relative_to(root)), recursive=False)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_bytes': size, 'entries': len(files)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--credential', required=True)
    args = parser.parse_args()
    credential = Path(args.credential)
    with (HERE/'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        protocol = validate()
        key = credential.read_text().strip()
        state = {'state': 'running', 'completed': 0, 'total': 3, 'active': None, 'results': []}
        stopped = threading.Event()
        def heartbeat():
            while not stopped.is_set():
                atomic_json(HERE/'health.json', dict(state, updated=time.time()))
                stopped.wait(30)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            for task_id in protocol['tasks']:
                state['active'] = task_id
                result = run_one(task_id, key)
                artifact = export(task_id)
                row = {k: result.get(k) for k in ['submitted', 'stop_reason', 'interaction_rounds', 'tool_calls']}
                row.update(task_id=task_id, artifact=artifact, official_success=None)
                state['results'].append(row)
                state['completed'] += 1
                atomic_json(HERE/'summary.json', state['results'])
                if result.get('stop_reason') == 'api_error':
                    raise RuntimeError('API error; remaining tasks not started, no automatic retry')
            state.update(state='completed', active=None)
        except Exception as error:
            state.update(state='failed', error_type=type(error).__name__)
            raise
        finally:
            stopped.set()
            thread.join(timeout=3)
            atomic_json(HERE/'health.json', dict(state, updated=time.time()))
            credential.unlink(missing_ok=True)
            key = ''

if __name__ == '__main__':
    main()
