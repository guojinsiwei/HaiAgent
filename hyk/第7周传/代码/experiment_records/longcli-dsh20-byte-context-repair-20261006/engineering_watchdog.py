"""One scoped program-only supervisor for the already-running DSH resume.

No model requests, no credentials/environment reads, no automatic restart.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from common import ROOT, save
from pause_campaign import processes, descendants
from recover_artifacts import export_source


def fault(health):
    if health.get('errors'):
        return 'controller_engineering_error'
    for task in health.get('active', []):
        directory = ROOT / 'jobs' / ('dsh--' + task)
        path = directory / 'health.json'
        status = json.loads(path.read_text()) if path.exists() else {}
        if status.get('state') == 'engineering_failure':
            return 'task_engineering_failure:' + task
        api = directory / 'api'
        if (api / 'relay-error.json').exists():
            return 'provider_transport_failure:' + task
        for path in api.glob('call-*.json'):
            if json.loads(path.read_text()).get('status') in (400, 401, 403, 429):
                return 'provider_http_failure:' + task
    return None


def stop(health, reason):
    pid = health['pid']
    argv = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    assert str(ROOT / 'resume_worker.py').encode() in argv, 'Refuse foreign process'
    launch = json.loads((ROOT / 'resume-launch.json').read_text())
    assert launch['pid'] == pid and pid != os.getpid()
    os.kill(pid, signal.SIGSTOP)
    selected = descendants(processes(), pid)
    for child in selected - {pid}:
        try: os.kill(child, signal.SIGSTOP)
        except ProcessLookupError: pass
    selected |= descendants(processes(), pid)
    for child in selected - {pid}:
        try: os.kill(child, signal.SIGSTOP)
        except ProcessLookupError: pass
    health = json.loads((ROOT / 'health-0.json').read_text())
    save(ROOT / 'health-before-engineering-watchdog.json', health)
    for child in sorted(selected - {pid}, reverse=True):
        try: os.kill(child, signal.SIGKILL)
        except ProcessLookupError: pass
    os.kill(pid, signal.SIGKILL)
    time.sleep(1)
    table = processes()
    assert not [p for p in selected if p in table and not table[p][2].startswith('Z')], 'Stop unconfirmed'
    interrupted = set(health.get('active', []))
    for directory in (ROOT / 'jobs').glob('dsh--*'):
        path = directory / 'health.json'
        if path.exists() and json.loads(path.read_text()).get('state') in ('preparing', 'running'):
            interrupted.add(directory.name[5:])
    frozen = []
    for task in sorted(interrupted):
        job = 'dsh--' + task
        root = ROOT / 'roots' / hashlib.sha256(job.encode()).hexdigest()[:16] / 'app'
        entry = {'task': task, 'source_retained': str(root)}
        if root.exists():
            try:
                entry['artifact'] = export_source(root, ROOT / 'jobs' / job / 'watchdog-stopped-source.tar.gz', True)
            except Exception as error:
                entry['snapshot_error_type'] = type(error).__name__
        frozen.append(entry)
    record = {'state': 'stopped', 'time': time.time(), 'reason': reason, 'interrupted': frozen,
              'worker_and_descendants_stopped': True, 'automatic_restart': False, 'model_calls': 0}
    save(ROOT / 'engineering-watchdog-stop.json', record)
    health.update(state='needs_attention', updated=time.time(), active=[],
                  pending=[t for t in health.get('pending', []) if t not in interrupted],
                  interrupted=sorted(interrupted), engineering_watchdog_stop=record)
    save(ROOT / 'health-0.json', health)


def main():
    while True:
        health = json.loads((ROOT / 'health-0.json').read_text())
        if not Path(f'/proc/{health["pid"]}').exists():
            save(ROOT / 'engineering-watchdog-health.json', {'state': 'worker_ended', 'updated': time.time(), 'model_calls': 0})
            return
        reason = fault(health)
        if reason:
            stop(health, reason)
            return
        if health['state'] == 'generation_complete' and not health.get('active'):
            return
        save(ROOT / 'engineering-watchdog-health.json', {'state': 'guarding', 'updated': time.time(),
            'active': health.get('active'), 'model_calls': 0})
        time.sleep(2)


if __name__ == '__main__':
    if '--start' in sys.argv:
        os.close(os.open(ROOT / 'engineering-watchdog.claim', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        with (ROOT / 'engineering-watchdog.log').open('x') as out, (ROOT / 'engineering-watchdog-stderr.log').open('x') as err:
            process = subprocess.Popen([sys.executable, '-B', __file__], stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True, cwd=ROOT)
        save(ROOT / 'engineering-watchdog-launch.json', {'pid': process.pid, 'model_calls': 0})
        print(json.dumps({'state': 'supervisor_started', 'pid': process.pid, 'model_calls': 0}))
    else:
        main()
