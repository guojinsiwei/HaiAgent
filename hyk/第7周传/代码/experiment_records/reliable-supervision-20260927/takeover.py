"""Replace only the old orchestration PIDs; keep trials and frozen sources intact."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from supervisor import Supervisor, identity, read, write


def main():
    root = Path(sys.argv[1]).resolve()
    kind = sys.argv[2]
    manager = Supervisor(root, kind)
    rows, active, blockers = manager.collect()
    if blockers:
        raise RuntimeError('Cannot safely take over: '+json.dumps(blockers))
    old_script = str(root/('durable.py' if kind == 'college' else 'supervise.py'))
    processes = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        try:
            args = (entry/'cmdline').read_bytes().decode().split('\0')
        except (OSError, UnicodeError): continue
        if old_script not in args: continue
        index = args.index(old_script)
        if len(args) <= index+2: continue
        mode = args[index+1]
        if mode in {'guard', 'scheduler'}:
            if mode in processes: raise RuntimeError('Multiple old '+mode+' processes')
            processes[mode] = (int(entry.name), identity(int(entry.name)), args[index+2])
    if set(processes) != {'guard', 'scheduler'}:
        raise RuntimeError('Expected exactly one old guard and scheduler')
    credential = Path(processes['guard'][2])
    if str(credential) != processes['scheduler'][2] or not credential.is_file():
        raise RuntimeError('Credential handoff unavailable')
    if credential.stat().st_uid != os.getuid() or credential.stat().st_mode & 0o077:
        raise RuntimeError('Credential permissions not private')
    old_health = read(root/'health.json')
    write(root/'supervision-before-v2.json', old_health)
    trial_pids = {r['job']: r.get('pid') for r in active}
    # SIGTERM to the two exact orchestration PIDs only, never to process groups.
    for mode in ('guard', 'scheduler'):
        pid, start, _ = processes[mode]
        if identity(pid) != start: raise RuntimeError('PID identity changed during handoff')
        os.kill(pid, signal.SIGTERM)
        until = time.monotonic()+10
        while identity(pid) == start and time.monotonic() < until: time.sleep(.1)
        if identity(pid) == start: raise RuntimeError('Old orchestration did not exit')
    script = Path(__file__).with_name('supervisor.py').resolve()
    with (root/'supervisor-v2.log').open('a') as log:
        child = subprocess.Popen([sys.executable, '-B', str(script), 'guard', str(root), kind, str(credential)],
                                 cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    write(root/'supervision-migration-v2.json', dict(time=time.time(),
        supervisor_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
        previous_protocol_sha256=old_health.get('protocol_sha256'),
        preserved_trial_pids=trial_pids, guard_pid=child.pid,
        changes='Dispatch recovered auxiliary errors; isolate local failures; monitor and restart scheduler. Frozen methods/budgets unchanged.'))
    until = time.monotonic()+90
    while time.monotonic() < until:
        state = read(root/'health.json', {})
        if state.get('supervision_version') == 'supervision-v2':
            print(json.dumps(dict(state=state['state'], completed=state['completed'],
                                  pending=state['pending'], active=state['active'],
                                  preserved_trial_pids=trial_pids)))
            return
        if child.poll() is not None: raise RuntimeError('New guard exited; inspect supervisor-v2.log')
        time.sleep(1)
    raise RuntimeError('Takeover heartbeat not confirmed; do not launch duplicate')


if __name__ == '__main__': main()
