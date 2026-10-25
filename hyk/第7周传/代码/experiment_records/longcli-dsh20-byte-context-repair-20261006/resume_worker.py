"""Resume exactly the four never-started worker-0 tasks, no previous trial rerun."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import time
import runner
from common import ROOT, save
from recover_artifacts import export_source

EXPECTED = ['61810_lock', '61810_net', '61810_syscall', '61810_traps']


def preflight():
    from check_ready import check
    check(0)
    health = json.loads((ROOT / 'health-0.json').read_text())
    assert health['state'] == 'needs_attention' and not health['active']
    assert health['pending'] == EXPECTED
    try:
        os.kill(health['pid'], 0)
    except ProcessLookupError:
        pass
    else:
        raise RuntimeError('Previous worker still alive')
    assert all(not (ROOT / 'jobs' / ('dsh--' + task)).exists() for task in EXPECTED)
    assert all(r.get('artifact') and r['task_processes_stopped'] for r in health['completed'])
    assert not (ROOT / 'resume-four.claim').exists(), 'Recovery already claimed; inspect public health'
    return health


def run(key):
    health = json.loads((ROOT / 'health-0.json').read_text())
    assert health['pending'] == EXPECTED and not health['active']
    rows = {r['task']: r for r in json.loads((ROOT / 'protocol.json').read_text())['tasks']}
    resources = json.loads((runner.BASE / 'resources-0.json').read_text())
    pending = [rows[t] for t in EXPECTED]
    completed, active, paused = list(health['completed']), {}, False
    runner.export_tree = export_source  # Transport only; accepted solver/adapter unchanged.
    os.environ['LONGCLI_WORKER'] = '0'
    health.update(pid=os.getpid(), resume_started=time.time(), resumed_never_started_only=True,
                  prior_errors=list(health.get('errors', [])), errors=[], state='running')
    with ThreadPoolExecutor(max_workers=2) as pool:
        while pending or active:
            occupied = {slot for _, slot in active.values()}
            for slot in range(2):
                if pending and not paused and slot not in occupied:
                    row = pending.pop(0)
                    active[pool.submit(runner.run_trial, row, resources['cpu_slots'][slot], key)] = (row, slot)
            for future in list(active):
                if not future.done():
                    continue
                row, _ = active.pop(future)
                result = future.result()
                completed.append(result)
                api = ROOT / 'jobs' / result['job'] / 'api'
                calls = [json.loads(p.read_text()) for p in api.glob('call-*.json')]
                failure = runner.admission_failure(result, calls, (api / 'relay-error.json').exists())
                if failure:
                    paused = True
                    health['errors'].append({'task': row['task'], 'reason': failure, 'no_auto_retry': True})
            health.update(updated=time.time(), state='admission_paused' if paused else 'running',
                          active=[r['task'] for r, _ in active.values()],
                          pending=[r['task'] for r in pending], completed=completed)
            save(ROOT / 'health-0.json', health)
            if paused and not active:
                break
            time.sleep(5)
    health.update(state='needs_attention' if pending else 'generation_complete', updated=time.time())
    save(ROOT / 'health-0.json', health)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--credential-file', type=Path, required=True)
    args = parser.parse_args()
    credential = args.credential_file
    assert credential.parent == Path('/dev/shm') and credential.name.startswith('longcli-dsh-resume-')
    assert credential.stat().st_mode & 0o077 == 0
    key = credential.read_text().strip()
    credential.unlink()
    run(key)
