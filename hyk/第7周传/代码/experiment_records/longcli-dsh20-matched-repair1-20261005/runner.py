"""Official DSH on the historical Cube private rootfs; fresh root/home per task."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time

from common import ROOT, PYTHON, export_tree, save, sha
from device_setup import prepare_devices
from provider import Relay, native_finish

BASE = Path('/mnt/lizh639/longcli-dh-raw-full20-20261004')
NODE = '/opt/dsh/node/package/bin/node'
BIN = '/opt/dsh/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js'


def own(path):
    for parent, dirs, files in os.walk(path, followlinks=False):
        os.chown(parent, 65534, 65534, follow_symlinks=False)
        for name in dirs + files:
            os.chown(Path(parent) / name, 65534, 65534, follow_symlinks=False)


def fresh_root(row, job):
    # Linux Unix-socket addresses have a 108-byte limit. The human-readable
    # job name remains in logs; use a bounded, collision-checked private root.
    root = ROOT / 'roots' / hashlib.sha256(job.encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=False)
    subprocess.run(['cp', '-a', '--reflink=auto', str(BASE / 'templates' / row['family']) + '/.', str(root)],
                   check=True, timeout=600)
    app = root / 'app'
    app.mkdir(exist_ok=True)
    for source in (BASE / 'public' / row['task']).iterdir():
        if source.is_dir():
            shutil.copytree(source, app / source.name, symlinks=True)
        else:
            shutil.copy2(source, app / source.name)
    own(app)
    own(root / 'tmp')
    for name in ('dsh-home', 'audit', 'dsh-relay'):
        (root / name).mkdir()
        own(root / name)
    (root / 'opt').mkdir(exist_ok=True)
    subprocess.run(['cp', '-a', '--reflink=auto', str(ROOT / 'runtime'), str(root / 'opt/dsh')], check=True, timeout=600)
    (root / 'opt/experiment').mkdir()
    for name in ('budget.mjs', 'experiment.patch.yml'):
        shutil.copy2(ROOT / name, root / 'opt/experiment' / name)
    assert not (root / 'tests/run-tests.sh').exists()
    prepare_devices(root)
    return root


class UnixRelay(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, filename, relay):
        class Forward(socketserver.BaseRequestHandler):
            def handle(self):
                with socket.create_connection(('127.0.0.1', relay.server.server_port), timeout=95) as upstream:
                    peers = [self.request, upstream]
                    while True:
                        readable, _, _ = select.select(peers, [], [], 95)
                        if not readable:
                            return
                        for source in readable:
                            chunk = source.recv(65536)
                            if not chunk:
                                return
                            (upstream if source is self.request else self.request).sendall(chunk)
        super().__init__(str(filename), Forward)
        os.chmod(filename, 0o600)
        os.chown(filename, 65534, 65534)
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()


def run_trial(row, cpus, key=None, mock=False, suffix='', pressure_steps=0):
    job = ('keyless' if mock else 'dsh') + '--' + row['task'] + suffix
    directory = ROOT / ('acceptance-jobs' if mock else 'jobs') / job
    directory.mkdir(parents=True, exist_ok=False)
    summary = {'job': job, 'task': row['task'], 'state': 'preparing', 'started': time.time(),
               'fresh_rootfs': True, 'fresh_home': True, 'worker': os.environ.get('LONGCLI_WORKER'),
               'runtime_version': '0.2.0-rc.2', 'api_key_visible_in_task': False, 'paid': not mock}
    save(directory / 'health.json', summary)
    relay = bridge = process = None
    try:
        root = fresh_root(row, job)
        api = directory / 'api'
        api.mkdir()
        relay = Relay(key, '127.0.0.1', api, mock=mock, pressure_steps=pressure_steps)
        bridge = UnixRelay(root / 'dsh-relay/proxy.sock', relay)
        task = ('Run the keyless integration check.' if mock else row['instruction'])
        task += ('\nExperiment limits: 800 logical model requests including auxiliary calls; at most two wire attempts per decision; '
                 '600 tools, 4096 output tokens per call, 48000 UTF-8 input bytes including tool declarations. '
                 'Keep file edits small enough to fit the output allowance. Work in /app; /tmp is not delivered. '
                 'External task networking and hidden tests are unavailable. Submit when ready; an exit code of zero is not a passing grade.')
        spec = {'proxy_token': relay.token, 'argv': [NODE, '--max-old-space-size=1024', '--disable-wasm-trap-handler', BIN,
                '--profile', 'headless', '--patch', '/opt/experiment/experiment.patch.yml', '--json', task]}
        argv = ['taskset', '-c', ','.join(map(str, cpus)), 'setpriv', '--reuid', '65534', '--regid', '65534', '--clear-groups',
                'unshare', '--user', '--map-root-user', '--pid', '--net', '--fork', '--kill-child=KILL',
                PYTHON, str(ROOT / 'isolated_entry.py'), str(root), json.dumps(spec)]
        summary.update(state='running', resources={'cpu_affinity': cpus, 'address_space_gib_per_process': 3})
        with (directory / 'console.jsonl').open('x') as output, (directory / 'stderr.log').open('x') as error:
            process = subprocess.Popen(argv, stdout=output, stderr=error, start_new_session=True, close_fds=True)
            deadline = time.time() + (360 if mock else row['wall_seconds'])
            while process.poll() is None:
                if time.time() >= deadline:
                    summary['stop_reason'] = 'wall_budget'
                    os.killpg(process.pid, 15)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, 9)
                        process.wait(timeout=10)
                    break
                summary.update(updated=time.time(), api_attempts=relay.calls, usage=dict(relay.usage))
                save(directory / 'health.json', summary)
                time.sleep(1 if mock else 5)
        # Kill orphan/background members before delivering a frozen workspace.
        try:
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass
        finish = native_finish(directory / 'console.jsonl')
        events = [json.loads(line) for line in (root / 'audit/events.jsonl').read_text().splitlines()]
        stops = [e['reason'] for e in events if e['event'] == 'budget_stop']
        summary.update(exit_code=process.returncode, native_finish_reason=finish, api_attempts=relay.calls, usage=dict(relay.usage),
                       logical_model_requests=max((e.get('logical_requests', 0) for e in events if e['event'] == 'model_stream'), default=0),
                       root_tool_dispatches=sum(e['event'] == 'tool_start' and not e.get('nested') for e in events),
                       all_model_streams=sum(e['event'] == 'model_stream' for e in events))
        summary.setdefault('stop_reason', stops[-1] if stops else 'native_' + str(finish))
        shutil.copyfile(root / 'audit/events.jsonl', directory / 'events.jsonl')
        contexts = [json.loads(f.read_text()) for f in sorted(api.glob('context-*.json'))]
        summary['maximum_input_bytes'] = max((c['after_bytes'] for c in contexts), default=0)
        if mock:
            assert finish == 'completed' and process.returncode == 0, 'Official native DSH fixture failed'
            assert summary['maximum_input_bytes'] <= 48000
            actor = [json.loads(f.read_text()) for f in sorted(api.glob('request-*.json'))]
            actor = [b for b in actor if any(t.get('function', {}).get('name') == 'bash' for t in b.get('tools', []))
                     and 'You are now acting as a compaction engine' not in str(b['messages'][-1].get('content', ''))]
            assert actor and all(b['max_tokens'] == 4096 for b in actor), 'Output allowance collapsed'
            assert summary['root_tool_dispatches'] == (pressure_steps + 1 if pressure_steps else 2)
            assert '/dev/null: Permission denied' not in json.dumps(events)
            assert not any(c.get('rejected_before_provider') or c.get('dropped_messages') for c in contexts)
            summary['native_compactions'] = sum(e['event'] == 'native_compaction' and e['type'] == 'compaction/end' for e in events)
            if pressure_steps:
                assert summary['native_compactions'] > 0, 'Native durable compaction never committed'
                assert (root / 'app/continuity-proof.txt').read_text().strip() == relay.mock_fact
                summary['early_evidence_survived_and_used'] = True
            summary['state'] = 'keyless_pass'
        else:
            summary['artifact'] = export_tree(root / 'app', directory / 'final-source.tar.gz', source_only=True)
            summary['state'] = 'awaiting_grade'
    except Exception as error:
        summary.update(state='engineering_failure', error_type=type(error).__name__, error=str(error)[:700])
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=15)
        if bridge:
            bridge.shutdown()
            bridge.server_close()
        if relay:
            relay.close()
        summary.update(ended=time.time(), seconds=time.time() - summary['started'], task_processes_stopped=True)
        save(directory / 'summary.json', summary)
        save(directory / 'health.json', summary)
    return summary


def admission_failure(result, calls, transport_failed=False):
    if result['state'] == 'engineering_failure' or not result.get('task_processes_stopped'):
        return 'engineering_failure'
    if result.get('stop_reason') not in ('native_completed', 'native_max-tokens', 'tool_budget', 'model_budget', 'wall_budget'):
        return result.get('stop_reason') or 'missing_native_finish'
    if transport_failed:
        return 'provider_transport_failure'
    if any(c.get('status') in (400, 401, 403, 429) for c in calls):
        return 'provider_http_failure'
    return None


def worker(worker_id, key):
    protocol = json.loads((ROOT / 'protocol.json').read_text())
    resources = json.loads((BASE / f'resources-{worker_id}.json').read_text())
    rows = [r for r in protocol['tasks'] if r['index'] % 2 == worker_id]
    pending, active, completed = list(rows), {}, []
    paused = False
    health = {'state': 'running', 'worker': worker_id, 'pid': os.getpid(), 'new_api_key': True, 'errors': []}
    with ThreadPoolExecutor(max_workers=2) as pool:
        while pending or active:
            occupied = {slot for _, slot in active.values()}
            for slot in range(2):
                if pending and not paused and slot not in occupied:
                    row = pending.pop(0)
                    active[pool.submit(run_trial, row, resources['cpu_slots'][slot], key)] = (row, slot)
            for future in list(active):
                if not future.done():
                    continue
                row, slot = active.pop(future)
                result = future.result()
                completed.append(result)
                api = ROOT / 'jobs' / result['job'] / 'api'
                calls = [json.loads(f.read_text()) for f in api.glob('call-*.json')]
                # Native output exhaustion is a measured model/budget failure,
                # not a reason to enlarge budgets or replace scored attempts.
                failure = admission_failure(result, calls, (api / 'relay-error.json').exists())
                if failure:
                    paused = True
                    health['errors'].append({'task': row['task'], 'reason': failure, 'no_auto_retry': True})
            health.update(updated=time.time(), state='admission_paused' if paused else 'running',
                          active=[r['task'] for r, _ in active.values()], pending=[r['task'] for r in pending],
                          completed=completed)
            save(ROOT / f'health-{worker_id}.json', health)
            if paused and not active:
                break
            time.sleep(5)
    health.update(state='needs_attention' if pending else 'generation_complete', updated=time.time())
    save(ROOT / f'health-{worker_id}.json', health)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=int, required=True)
    parser.add_argument('--credential-file', type=Path, required=True)
    args = parser.parse_args()
    credential = args.credential_file
    assert credential.parent == Path('/dev/shm') and credential.name.startswith('longcli-dsh-matched-')
    assert credential.stat().st_mode & 0o077 == 0
    key = credential.read_text().strip()
    credential.unlink()
    worker(args.worker, key)
