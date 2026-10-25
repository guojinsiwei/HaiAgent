"""Out-of-band bounded recovery. Never edit frozen code, task state or protocol."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROJECT = Path('/mnt/lizh639/BestFGS-compare-v4')
OUTPUT = Path('/mnt/lizh639/bestfgs-runs/swe100-paired-v2')
PREPARED = Path('/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen')
PYTHON = '/mnt/lizh639/envs/bestfgs/bin/python'
PROTOCOL_SHA = '8ed0e6c5e01e920a7c3b2065ae5a1e269e622578c9fc469753ffb7738f350f9d'
MAX_ATTEMPTS = 3  # Includes the original attempt, not three additional retries.
MAX_RESTARTS = 20  # Per shard, persisted in the append-only event journal.
POLL_SECONDS = 30


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def process_matches(argv, index):
    if str(PROJECT / 'run_comparison.py') not in argv or 'run' not in argv:
        return False
    try:
        return argv[argv.index('--shard-index') + 1] == str(index) and argv[argv.index('--output-root') + 1] == str(OUTPUT)
    except (ValueError, IndexError):
        return False


def processes(index, identities):
    runners, orphans = [], []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            argv = [item.decode(errors='replace') for item in (path / 'cmdline').read_bytes().split(b'\0') if item]
            if not argv or 'python' not in Path(argv[0]).name:
                continue
            if process_matches(argv, index):
                runners.append(int(path.name))
            elif str(PROJECT / 'run_notebook.py') in argv and '--output-root' in argv:
                run_root = Path(argv[argv.index('--output-root') + 1])
                if OUTPUT in run_root.parents and any(i in run_root.parts for i in identities):
                    orphans.append(int(path.name))
            elif '-m' in argv and any(module in argv for module in ('bestfgs', 'bestfgs.raw_baseline')):
                if '--run-root' in argv:
                    run_root = Path(argv[argv.index('--run-root') + 1])
                    if OUTPUT in run_root.parents and any(i in run_root.parts for i in identities):
                        orphans.append(int(path.name))
        except (OSError, ValueError, IndexError):
            continue
    return runners, orphans


def retry_reason(state, log_tail):
    if state.get('status') != 'search_error':
        return False, 'unclassified_interrupted_state'
    if state.get('attempt_count', 1) >= MAX_ATTEMPTS:
        return False, 'task_retry_limit'
    if state.get('error'):
        return False, 'runner_validation_error'
    if state.get('stop_reason') != 'model_unavailable' or state.get('model_usage', {}).get('last_failure_kind') != 'transport':
        return False, 'not_transport_failure'
    errors = [line for line in log_tail.splitlines() if '本次模型请求未成功' in line or 'HTTP请求失败' in line]
    last = errors[-1] if errors else ''
    if any(f'状态码={code}' in last for code in (400, 401, 402, 403, 404)):
        return False, 'credential_balance_or_request_error'
    approved = ('Temporary failure in name resolution', 'URLError', 'TimeoutError', 'timed out',
                'ConnectionResetError', 'Connection reset', 'RemoteDisconnected', '状态码=429',
                '状态码=500', '状态码=502', '状态码=503', '状态码=504', '_TransportFailure')
    return (True, 'transient_transport') if any(word in last for word in approved) else (False, 'unknown_transport_failure')


def decide(states, tails, restarts):
    failures = [(key, value) for key, value in states.items() if value and value.get('status') != 'completed']
    if all(value and value.get('status') == 'completed' for value in states.values()):
        return 'completed', []
    if restarts >= MAX_RESTARTS:
        return 'needs_attention', ['shard_restart_limit']
    reasons = []
    for key, value in failures:
        ok, reason = retry_reason(value, tails.get(key, ''))
        if not ok:
            reasons.append(f'{key}:{reason}')
    if reasons:
        return 'needs_attention', reasons
    return 'recover' if failures else 'continue_pending', [key for key, _ in failures]


def tail(path):
    if not path.is_file():
        return ''
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 12000))
        return stream.read().decode('utf-8', errors='replace')


def api_probe(key):
    request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            models = [row.get('id') for row in json.load(response).get('data', [])]
        return 'ok' if 'deepseek-flash' in models else 'model_missing'
    except urllib.error.HTTPError as exc:
        return f'http_{exc.code}'
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 'network_unavailable'


class Guard:
    def __init__(self, index):
        self.index = index
        self.health = OUTPUT / 'health'
        self.health.mkdir(parents=True, exist_ok=True)
        self.journal = self.health / f'events-{index}.jsonl'
        self.child = None
        self.log_stream = None
        self.next_probe = 0
        self.probe_failures = 0
        self.plan = read_json(OUTPUT / 'comparison-protocol.json')
        if canonical(self.plan) != PROTOCOL_SHA:
            raise ValueError('Frozen protocol changed')
        self.ids = self.plan['sharding']['workers'][index]
        self.restarts = 0
        if self.journal.exists():
            for line in self.journal.read_text().splitlines():
                self.restarts += json.loads(line).get('event') == 'launch'
        self.permanent_block = None

    def event(self, name, **details):
        record = dict(event=name, at=datetime.now(timezone.utc).isoformat(), index=self.index, **details)
        with self.journal.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def status(self, state, **details):
        from benchmark_runtime import atomic_write_json
        atomic_write_json(self.health / f'worker-{self.index}.json', dict(
            status=state, checked_at=datetime.now(timezone.utc).isoformat(), guard_pid=os.getpid(),
            hostname=os.uname().nodename, shard_index=self.index, protocol_sha256=PROTOCOL_SHA,
            max_attempts_per_method_task=MAX_ATTEMPTS, recovery_launches=self.restarts,
            guard_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), **details))

    def command(self, action):
        return [PYTHON, str(PROJECT / 'run_comparison.py'), action, '--plan', str(PREPARED / 'task-plan.json'),
                '--prepared-root', str(PREPARED), '--output-root', str(OUTPUT),
                '--shard-count', '2', '--shard-index', str(self.index)]

    def tick(self):
        if self.child is not None and self.child.poll() is not None:
            self.event('runner_exit', exit_code=self.child.returncode)
            self.child = None
            self.log_stream.close()
            self.log_stream = None
        states, tails = {}, {}
        for method in ('bestfgs', 'raw'):
            for identity in self.ids:
                key = f'{method}/{identity}'
                value = read_json(OUTPUT / method / 'states' / f'{identity}.json')
                states[key] = value
                if value and value.get('status') != 'completed' and value.get('attempt'):
                    tails[key] = tail(Path(value['attempt']) / 'agent.log')
        counts = dict(Counter(value.get('status') if value else 'pending' for value in states.values()))
        output_failures = sum(bool(value and value.get('model_usage', {}).get('last_failure_kind') == 'model_output') for value in states.values())
        free_gb = round(shutil.disk_usage(OUTPUT).free / 2**30, 1)
        runners, orphans = processes(self.index, self.ids)
        summary = dict(counts=counts, model_output_failures=output_failures, free_gb=free_gb, runner_pids=runners)
        if len(runners) > 1:
            self.status('needs_attention', reason='duplicate_runner', **summary)
            return
        if runners:
            # Heartbeats measure freshness but never kill a slow live task.
            active = []
            for key, state in states.items():
                if state and state.get('status') == 'running':
                    method, identity = key.split('/', 1)
                    child = read_json(OUTPUT / method / 'search' / identity / identity / 'status.json', {})
                    log = Path(child.get('attempt', '/nonexistent')) / 'agent.log'
                    age = round(time.time() - log.stat().st_mtime) if log.exists() else None
                    active.append({'task': key, 'log_age_seconds': age})
            stale = any(row['log_age_seconds'] is not None and row['log_age_seconds'] > 1800 for row in active)
            self.status('running_stale_log' if stale else 'running', active=active, **summary)
            return
        if orphans:
            self.status('needs_attention', reason='orphan_agent_do_not_duplicate', orphan_pids=orphans, **summary)
            return
        decision, reasons = decide(states, tails, self.restarts)
        if decision == 'completed':
            self.status('completed', **summary)
            self.event('completed')
            return 'done'
        if decision == 'needs_attention' or self.permanent_block:
            self.status('needs_attention', reasons=reasons, reason=self.permanent_block, **summary)
            return
        if free_gb < 20 or shutil.disk_usage('/tmp').free < 2 * 2**30:
            self.status('needs_attention', reason='low_disk_space', **summary)
            return
        if time.monotonic() < self.next_probe:
            self.status('waiting_for_network', retry_in_seconds=round(self.next_probe - time.monotonic()), **summary)
            return
        result = api_probe(os.environ['DEEPSEEK_API_KEY'])
        if result != 'ok':
            self.probe_failures += 1
            self.next_probe = time.monotonic() + min(600, 60 * 2 ** min(self.probe_failures - 1, 4))
            self.event('preflight_unavailable', result=result)
            if result in ('http_400', 'http_401', 'http_402', 'http_403', 'http_404', 'model_missing'):
                self.permanent_block = result
            self.status('needs_attention' if self.permanent_block else 'waiting_for_network', reason=result, **summary)
            return
        env = dict(os.environ, PYTHONPATH=str(PROJECT / 'src'), PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1')
        checked = subprocess.run(self.command('plan'), cwd=PROJECT, env=env, capture_output=True, text=True, timeout=90)
        if checked.returncode or json.loads(checked.stdout)['protocol_sha256'] != PROTOCOL_SHA:
            self.permanent_block = 'code_config_or_environment_changed'
            self.status('needs_attention', reason=self.permanent_block, **summary)
            return
        # Serialize launch with the original worker lock. Frozen runner reacquires it.
        from run_notebook import run_lock
        with run_lock(OUTPUT / 'worker-locks' / str(self.index)):
            if processes(self.index, self.ids)[0]:
                return
        command = self.command('run')
        if decision == 'recover':
            command.append('--retry-infrastructure')
        self.event('launch', decision=decision, failed_tasks=reasons, previous_attempts={key: states[key].get('attempt_count', 1) for key in reasons})
        self.restarts += 1
        self.log_stream = (OUTPUT / f'worker-{self.index}.console.log').open('a', encoding='utf-8')
        self.child = subprocess.Popen(command, cwd=PROJECT, env=env, stdout=self.log_stream, stderr=self.log_stream, start_new_session=True)
        self.next_probe = time.monotonic() + 60
        self.probe_failures = 0
        self.status('recovering', child_pid=self.child.pid, **summary)

    def run(self):
        from run_notebook import run_lock
        with run_lock(self.health / f'guard-lock-{self.index}'):
            self.event('guard_started', max_attempts=MAX_ATTEMPTS, max_restarts=MAX_RESTARTS)
            while True:
                try:
                    if self.tick() == 'done':
                        return
                except Exception as exc:
                    self.status('needs_attention', reason='guard_check_error', error_type=type(exc).__name__)
                    self.event('guard_check_error', error_type=type(exc).__name__)
                time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    sys.path[:0] = [str(PROJECT), str(PROJECT / 'src')]
    index = int(sys.argv[1])
    if os.uname().nodename != ['lizh639-aa91', 'lizh639-8e64'][index]:
        raise SystemExit('Wrong host')
    Guard(index).run()
