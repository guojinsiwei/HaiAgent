"""Freeze only old schedulers; preserve trials and graders during handover."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

from parallel_worker import alive, classify, read

ROOT = Path(__file__).resolve().parent
ARMS = [Path('/mnt/sdb/home/lizh639/longcli-resume-five-20261007/lats-resume-20261007'),
        Path('/mnt/sdb/home/lizh639/longcli-taco-clean20-20261007')]


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    os.replace(temporary, path)


def verify_controller(root, pid):
    assert alive(pid), 'Controller already ended: ' + root.name
    command = (Path('/proc') / str(pid) / 'cmdline').read_bytes()
    assert str(root / 'resume_worker.py').encode() in command, 'Unexpected controller'


def validate():
    assert not (ROOT / 'launch.claim').exists(), 'Already handed over'
    for root in ARMS:
        health = read(root / 'health.json')
        verify_controller(root, health['pid'])
        assert health.get('pending'), 'No remaining tasks: ' + root.name
        assert alive(read(root / 'grading-launch.json')['pid']), 'Grader not alive'
        assert not (root / 'parallel-go.json').exists()
        if read(root / 'resume-plan.json')['method'] == 'taco':
            assert not (root / 'taco-pool.json').exists(), 'Shared TACO pool present'
            assert 'task_local_linear' in (root / 'repair_runtime.py').read_text()


def snapshot(root, old_pid):
    deadline = time.time() + 25
    grader_pid = read(root / 'grading-launch.json')['pid']
    while True:
        plan = read(root / 'resume-plan.json')
        pending, active, done, errors = classify(root, plan)
        children_path = Path('/proc') / str(old_pid) / 'task' / str(old_pid) / 'children'
        children = {int(value) for value in children_path.read_text().split() if alive(int(value))}
        unknown = children - {grader_pid} - set(active)
        if not unknown:
            return {'pending': [row['task'] for row in pending], 'adopted_pids': list(active),
                    'completed': done, 'errors': errors}
        assert time.time() < deadline, 'Unidentified running child; handover cancelled'
        time.sleep(0.5)


def main():
    validate()
    if '--check' in sys.argv:
        print(json.dumps({'ready': True, 'concurrency_per_arm': 4,
                          'arms': [root.name for root in ARMS], 'paid_model_calls': 0}))
        return
    key = sys.stdin.readline().strip()
    assert key and not any(char.isspace() for char in key)
    request = urllib.request.Request('https://api.deepseek.com/models',
                                     headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(request, timeout=30) as response:
        assert any(model['id'] == 'deepseek-flash' for model in json.load(response)['data'])
    old_pids = {}
    new_children = {}
    committed = set()
    try:
        for root in ARMS:
            pid = read(root / 'health.json')['pid']
            verify_controller(root, pid)
            os.kill(pid, signal.SIGSTOP)
            old_pids[root] = pid
        for root, pid in old_pids.items():
            record = snapshot(root, pid)
            save(root / 'parallel-handover.json', dict(record, old_controller_pid=pid, time=time.time()))
            with (root / 'parallel-worker.log').open('x') as stdout, (root / 'parallel-stderr.log').open('x') as stderr:
                child = subprocess.Popen([sys.executable, '-B', str(ROOT / 'parallel_worker.py'), str(root)],
                                         cwd=root, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                         start_new_session=True, text=True)
                child.stdin.write(key + '\n')
                child.stdin.close()
            new_children[root] = child
            deadline = time.time() + 20
            while read(root / 'parallel-started.json').get('pid') != child.pid:
                assert child.poll() is None and time.time() < deadline, 'New controller failed readiness'
                time.sleep(0.2)
        # Every replacement is waiting at a gate; old trials and graders keep running.
        for root, old_pid in old_pids.items():
            for name in ('resume-plan.json', 'protocol.json'):
                path = root / name
                original = read(path)
                save(root / ('before-parallel-' + name), original)
                save(path, dict(original, concurrency=4))
            save(root / 'parallel-config.json', {'concurrency': 4})
            os.kill(old_pid, signal.SIGTERM)
            os.kill(old_pid, signal.SIGCONT)
            committed.add(root)
            save(root / 'parallel-go.json', {'time': time.time(), 'old_pid': old_pid})
        save(ROOT / 'launch.claim', {'time': time.time(), 'controllers':
             {root.name: process.pid for root, process in new_children.items()}})
        print(json.dumps({'state': 'started', 'concurrency_per_arm': 4,
                          'controllers': {root.name: process.pid for root, process in new_children.items()}}))
    except BaseException:
        for root, process in new_children.items():
            if root not in committed and process.poll() is None:
                process.kill()
        for root, pid in old_pids.items():
            if root not in committed and alive(pid):
                os.kill(pid, signal.SIGCONT)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'state': 'handover_failed', 'error_type': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
