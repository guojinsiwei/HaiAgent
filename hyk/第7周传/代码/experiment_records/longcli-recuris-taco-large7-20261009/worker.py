"""Independent task children; one local fault never kills healthy siblings."""
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
import time
from common import ROOT, save
from capacity import install, verify_protocol


def read(path): return json.loads(path.read_text()) if path.exists() else {}


def trial(row, key):
    from runner import run_trial
    install(row['method'])
    run_trial(row, key)


def classify(summary):
    if summary.get('cleanup_error'): return 'cleanup'
    if summary.get('stop_reason') in ('http_401', 'http_402', 'http_403'): return 'credential_or_balance'
    if summary.get('engineering_fault'): return summary['engineering_fault']
    return None


def worker(key):
    p = read(ROOT / 'protocol.json'); verify_protocol(p)
    method = p['methods'][0]; pending = list(p['tasks']); active = {}; finished = []; errors = []
    context = mp.get_context('fork'); paused = False; last_fault = None; same_fault = 0
    os.environ['TMPDIR'] = str(ROOT / 'host-tmp')
    import tempfile
    tempfile.tempdir = str(ROOT / 'host-tmp')
    h = {'state': 'running', 'pid': os.getpid(), 'started': time.time()}
    while pending or active:
        for slot, (child, row, began) in list(active.items()):
            job = method + '--' + row['task']; directory = ROOT / 'jobs' / job
            status = read(directory / 'health.json')
            expired = time.time() - began > 7380 or time.time() - status.get('updated', began) > 660
            if child.is_alive() and not expired: continue
            if child.is_alive(): child.kill()
            child.join(2)
            from sandbox import close_owned
            try: close_owned(directory)
            except Exception as exc:
                status['cleanup_error'] = type(exc).__name__
            summary = read(directory / 'summary.json')
            summary.update({k: status[k] for k in ('cleanup_error',) if k in status})
            fault = classify(summary) or ('deadline_or_stall' if expired else None)
            if child.exitcode != 0 or not summary.get('artifact'): fault = fault or 'missing_delivery'
            if fault:
                errors.append({'job': job, 'reason': fault, 'siblings_continue': True})
                same_fault = same_fault + 1 if fault == last_fault else 1; last_fault = fault
                if same_fault >= 2 or fault in ('credential_or_balance', 'cleanup'): paused = True
            else:
                last_fault = None; same_fault = 0
            finished.append(job); del active[slot]
        # One included canary per arm; explicit gate opens when it has delivered.
        capacity = p['concurrency'] if finished else 1
        for slot in range(capacity):
            if not paused and pending and slot not in active:
                row = dict(pending.pop(0), method=method)
                child = context.Process(target=trial, args=(row, key)); child.start()
                active[slot] = (child, row, time.time())
        h.update(updated=time.time(), active=[method + '--' + r['task'] for _, r, _ in active.values()],
                 completed=finished, pending=[r['task'] for r in pending], errors=errors,
                 paused_new_admission=paused)
        save(ROOT / 'health.json', h)
        if paused and not active: break
        time.sleep(3)
    h.update(state='needs_attention' if errors else 'generation_complete', active=[], updated=time.time())
    save(ROOT / 'health.json', h)
