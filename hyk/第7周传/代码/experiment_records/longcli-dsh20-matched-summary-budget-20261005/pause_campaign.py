"""User-authorized stop: verify worker identity, stop its descendants, retain evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from common import ROOT, save, export_tree


def processes():
    output = subprocess.check_output(['ps', '-eo', 'pid=,ppid=,pgid=,stat='], text=True)
    return {int(row[0]): (int(row[1]), int(row[2]), row[3]) for row in (line.split() for line in output.splitlines())}


def descendants(table, parent):
    selected = {parent}
    while True:
        expanded = selected | {pid for pid, row in table.items() if row[0] in selected}
        if expanded == selected:
            return selected
        selected = expanded


def main(worker):
    output = ROOT / f'pause-{worker}.json'
    if output.exists():
        print(output.read_text())
        return
    health_path = ROOT / f'health-{worker}.json'
    health = json.loads(health_path.read_text())
    pid = health['pid']
    if not Path(f'/proc/{pid}/cmdline').exists():
        health = json.loads(health_path.read_text())
        assert health['state'] in ('needs_attention', 'generation_complete', 'paused') and not health['active']
        save(ROOT / f'health-pre-pause-{worker}.json', health)
        record = {'state': 'paused', 'worker': worker, 'time': time.time(),
                  'reason': 'context_adapter_repair_worker_already_exited',
                  'worker_and_descendants_stopped': True, 'selected_process_count': 0,
                  'interrupted': [], 'finished_original_results_preserved': len(health['completed']),
                  'replacement_requires_new_hidden_input': True}
        save(output, record)
        health.update(state='paused', updated=time.time(), pause_record=output.name, user_requested_pause=True)
        save(health_path, health)
        print(json.dumps(record))
        return
    argv = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    assert str(ROOT / 'runner.py').encode() in argv, 'Refuse to signal a foreign process'
    assert b'--worker' in argv and argv[argv.index(b'--worker') + 1] == str(worker).encode()
    assert pid != os.getpid()
    os.kill(pid, signal.SIGSTOP)
    selected = descendants(processes(), pid)
    for child in selected - {pid}:
        try:
            os.kill(child, signal.SIGSTOP)
        except ProcessLookupError:
            pass
    selected |= descendants(processes(), pid)
    for child in selected - {pid}:
        try:
            os.kill(child, signal.SIGSTOP)
        except ProcessLookupError:
            pass
    save(ROOT / f'health-pre-pause-{worker}.json', health)
    # Killing the controller also destroys its in-RAM key. No credentials are
    # recovered from it for the replacement campaign.
    for child in sorted(selected - {pid}, reverse=True):
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
    os.kill(pid, signal.SIGKILL)
    time.sleep(1)
    table = processes()
    running = [p for p in selected if p in table and not table[p][2].startswith('Z')]
    assert not running, 'Stop could not be confirmed'
    frozen = []
    for task in health['active']:
        job = 'dsh--' + task
        directory = ROOT / 'jobs' / job
        root = ROOT / 'roots' / hashlib.sha256(job.encode()).hexdigest()[:16]
        workspace = root / 'app'
        if workspace.is_dir():
            archive = directory / 'paused-source.tar.gz'
            artifact = export_tree(workspace, archive, source_only=True)
            frozen.append({'task': task, 'job': job, 'artifact': artifact, 'status': 'user_interrupted_not_a_scored_rerun'})
    record = {'state': 'paused', 'worker': worker, 'time': time.time(), 'reason': 'user_requested_context_adapter_repair',
              'worker_and_descendants_stopped': True, 'selected_process_count': len(selected),
              'interrupted': frozen, 'finished_original_results_preserved': len(health['completed']),
              'replacement_requires_new_hidden_input': True}
    save(output, record)
    health.update(state='paused', updated=time.time(), active=[], interrupted=[r['task'] for r in frozen],
                  pause_record=output.name, user_requested_pause=True)
    save(health_path, health)
    print(json.dumps(record))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=int, required=True)
    main(parser.parse_args().worker)
