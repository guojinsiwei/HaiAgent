"""KZ2.0: exactly four authorized tasks, independent workers and grading."""
import json
import multiprocessing
import subprocess
import sys
import time
from pathlib import Path
from common import ROOT, save, validate
from guarded_trial import trial
from verify_contract import verify


def isolation_decision(error, consecutive):
    # Individual task faults never terminate unrelated tasks. Two consecutive
    # identical infrastructure faults pause NEW admissions, not active trials.
    if not error:
        return None, 0, False
    name = error.get('reason', 'unknown')
    old_name, old_count = consecutive
    count = old_count + 1 if name == old_name else 1
    return name, count, count >= 2


def worker(key):
    protocol = validate()
    verify()
    pending = [dict(row, method='1342') for row in protocol['tasks']]
    assert {r['task'] for r in pending} == {'61810_cow'}
    assert len(pending) == 1 and protocol['methods'] == ['1342']
    assert not list((ROOT/'jobs').glob('1342--*/summary.json'))
    ctx = multiprocessing.get_context('spawn')
    active = {}; done = []; errors = []; admission_paused = False
    last_error = (None, 0); pilot_complete = False
    with (ROOT/'grading-worker.log').open('x') as out, (ROOT/'grading-stderr.log').open('x') as err:
        subprocess.Popen([sys.executable, '-B', str(ROOT/'supplement_grader.py')],
                         stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                         start_new_session=True)
    try:
        while active or pending and not admission_paused:
            for job, (process, row) in list(active.items()):
                if process.is_alive():
                    continue
                process.join(); del active[job]; done.append(job)
                file = ROOT/'jobs'/job/'summary.json'
                summary = json.loads(file.read_text()) if file.exists() else {}
                reason = summary.get('engineering_fault') or ('missing_summary' if not summary else None)
                if process.exitcode and not reason and summary.get('stop_reason') != 'cost_budget_cny':
                    reason = 'worker_exit_' + str(process.exitcode)
                error = {'job': job, 'reason': reason} if reason else None
                if error:
                    errors.append(error)
                name, count, pause = isolation_decision(error, last_error)
                last_error = (name, count)
                admission_paused = admission_paused or pause
                pilot_complete = True
            limit = protocol['concurrency']  # keyless Docker/1342 smoke validated before admission
            while pending and len(active) < limit and not admission_paused:
                row = pending.pop(0); job = '1342--' + row['task']
                process = ctx.Process(target=trial, args=(row, key))
                process.start(); active[job] = (process, row)
            save(ROOT/'health.json', dict(name='KZ2.0',state='admission_paused' if admission_paused else 'running',
                updated=time.time(), active=list(active), completed=done,
                pending=['1342--'+r['task'] for r in pending], errors=errors,
                concurrency=protocol['concurrency'], preserved_original_tasks=20))
            time.sleep(3)
    finally:
        # No automatic killing of unrelated active trials upon one task fault.
        # On supervisor interruption, leave their evidence intact for inspection.
        save(ROOT/'health.json', dict(name='KZ2.0',state='needs_attention' if pending or active else 'generation_complete',
            updated=time.time(), active=list(active), completed=done,
            pending=['1342--'+r['task'] for r in pending], errors=errors,
            preserved_original_tasks=20))


if __name__ == '__main__':
    key = sys.stdin.readline().strip()
    assert key and not any(c.isspace() for c in key)
    worker(key)
