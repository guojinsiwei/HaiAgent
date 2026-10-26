"""Hot-adjust only concurrency to eight; report DH excluding cow and lock."""
import json
import os
from pathlib import Path
import statistics
import sys
import time

BASE = Path('/mnt/sdb/home/lizh639')
ARMS = [BASE / 'longcli-resume-five-20261007/lats-resume-20261007',
        BASE / 'longcli-taco-clean20-20261007']


def read(path):
    return json.loads(path.read_text())


def alive(pid):
    path = Path('/proc') / str(pid) / 'stat'
    return path.exists() and path.read_text().rsplit(')', 1)[1].split()[0] != 'Z'


def save(path, value):
    temporary = path.with_name(path.name + '.parallel8.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    os.replace(temporary, path)


def main():
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available_kib = int(memory['MemAvailable'].split()[0])
    print(json.dumps({'cpu_count': os.cpu_count(), 'available_memory_gib': available_kib / 1048576}))
    assert available_kib > 80 * 1048576, 'Insufficient headroom for eight additional 8GiB tasks'
    for root in ARMS:
        health = read(root / 'health.json')
        assert alive(health['pid']), 'Controller no longer running: ' + root.name
        command = (Path('/proc') / str(health['pid']) / 'cmdline').read_bytes()
        assert b'parallel_worker.py' in command and str(root).encode() in command
        assert health.get('pending'), 'No pending work: ' + root.name
        assert time.time() - health['updated'] < 60, 'Controller heartbeat stale'
    if '--apply' in sys.argv:
        for root in ARMS:
            old = read(root / 'parallel-config.json')
            save(root / ('parallel8-change-' + str(time.time_ns()) + '.json'),
                 {'before': old, 'after': {'concurrency': 8}, 'time': time.time(),
                  'task_budgets_changed': False, 'failed_tasks_retried': False,
                  'cow_repair_requested': False})
            save(root / 'parallel-config.json', dict(old, concurrency=8))
            print(json.dumps({'root': str(root), 'concurrency': 8, 'updated': True}))
    rows = {}
    dh = BASE / 'longcli-resume-five-20261007/dh-resume-20261007'
    preserved = read(dh / 'resume-plan.json')['preserved']
    records = preserved.values() if isinstance(preserved, dict) else preserved
    for row in records:
        report = read(Path(row['report']))
        rows[report['task']] = report
    for path in (dh / 'grades').glob('*/result.json'):
        report = read(path)
        if report.get('grading_state') == 'complete':
            rows[report['task']] = report
    selected = {task: row for task, row in rows.items()
                if task not in ['61810_cow', '61810_lock']}
    assert len(selected) == 18, 'Expected 18 unique official task scores'
    values = [row['f2p']['step_score'] for row in selected.values()]
    print(json.dumps({'DH_excluding_cow_lock': {'count': len(values), 'sum': sum(values),
                     'mean': statistics.mean(values),
                     'full_pass': sum(bool(row.get('official_success')) for row in selected.values()),
                     'lock_score': rows['61810_lock']['f2p']['step_score'],
                     'included_tasks': sorted(selected)}}))


if __name__ == '__main__':
    main()
