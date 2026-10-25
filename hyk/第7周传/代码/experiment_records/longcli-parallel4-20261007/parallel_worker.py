"""Adopt existing trials and fill unused slots; reload concurrency between ticks."""
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import sys
import time


def read(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}


def alive(pid):
    try:
        return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
    except (FileNotFoundError, ProcessLookupError):
        return False


def classify(root, plan, is_alive=alive):
    pending, active, done, errors = [], {}, [], []
    method = plan['method']
    for original in plan['run_tasks']:
        row = dict(original, method=method)
        job = method + '--' + row['task']
        directory = root / 'jobs' / job
        summary = read(directory / 'summary.json')
        health = read(directory / 'health.json')
        if summary:
            if summary.get('state') == 'awaiting_grade' and not summary.get('engineering_fault'):
                done.append(job)
            else:
                errors.append({'job': job, 'reason': summary.get('engineering_fault') or
                               summary.get('stop_reason') or 'previous_task_failure',
                               'other_tasks_continue': True})
        elif health and is_alive(health.get('pid')):
            active[health['pid']] = {'row': row, 'started': health['started'], 'process': None}
        elif directory.exists():
            errors.append({'job': job, 'reason': 'existing_incomplete_task_not_retried',
                           'other_tasks_continue': True})
        else:
            pending.append(row)
    return pending, active, done, errors


def main(root, key):
    sys.path.insert(0, str(root))
    from common import save
    from resume_worker import trial, cleanup, valid

    save(root / 'parallel-started.json', {'pid': os.getpid(), 'ready': True, 'time': time.time()})
    gate_deadline = time.time() + 60
    while not (root / 'parallel-go.json').exists():
        if time.time() > gate_deadline:
            return
        time.sleep(0.2)
    plan = read(root / 'resume-plan.json')
    pending, active, done, errors = classify(root, plan)
    context = mp.get_context('fork')
    os.environ['TMPDIR'] = str(root / 'host-tmp')
    import tempfile
    tempfile.tempdir = str(root / 'host-tmp')
    method = plan['method']
    health = {'state': 'running', 'pid': os.getpid(), 'started': time.time(), 'method': method,
              'reused_completed': len(plan['preserved']), 'errors': errors,
              'adopted_trials': [record['row']['task'] for record in active.values()]}
    try:
        while pending or active:
            for pid, record in list(active.items()):
                row = record['row']
                job = method + '--' + row['task']
                directory = root / 'jobs' / job
                status = read(directory / 'health.json')
                expired = (time.time() - record['started'] > row['wall_seconds'] + 180 or
                           time.time() - status.get('updated', record['started']) > 660)
                if alive(pid) and not expired:
                    continue
                if alive(pid):
                    os.kill(pid, signal.SIGKILL)
                process = record['process']
                if process is not None:
                    process.join(2)
                cleanup(job, method)
                summary = read(directory / 'summary.json')
                if valid(summary) and not expired:
                    done.append(job)
                else:
                    reason = 'deadline_or_stall' if expired else (
                        summary.get('engineering_fault') or summary.get('stop_reason') or 'missing_delivery')
                    errors.append({'job': job, 'reason': reason, 'other_tasks_continue': True})
                del active[pid]
            concurrency = read(root / 'parallel-config.json').get('concurrency', 4)
            assert type(concurrency) is int and 1 <= concurrency <= 8
            while pending and len(active) < concurrency:
                row = pending.pop(0)
                process = context.Process(target=trial, args=(row, key, len(active)))
                process.start()
                active[process.pid] = {'row': row, 'started': time.time(), 'process': process}
            health.update(state='running', updated=time.time(), concurrency=concurrency,
                          active=[method + '--' + record['row']['task'] for record in active.values()],
                          active_pids={record['row']['task']: pid for pid, record in active.items()},
                          pending=[row['task'] for row in pending], completed=done, errors=errors)
            save(root / 'health.json', health)
            time.sleep(3)
        health.update(state='needs_attention' if errors else 'generation_complete', active=[],
                      pending=[], updated=time.time())
        save(root / 'health.json', health)
    except BaseException as error:
        health.update(state='needs_attention', updated=time.time(), controller_error=type(error).__name__,
                      active=[method + '--' + record['row']['task'] for record in active.values()],
                      active_pids={record['row']['task']: pid for pid, record in active.items()},
                      pending=[row['task'] for row in pending])
        save(root / 'health.json', health)
        raise


if __name__ == '__main__':
    campaign_root = Path(sys.argv[1]).resolve()
    assert campaign_root.is_relative_to(Path('/mnt/sdb/home/lizh639'))
    credential = sys.stdin.readline().strip()
    assert credential and not any(char.isspace() for char in credential)
    main(campaign_root, credential)
