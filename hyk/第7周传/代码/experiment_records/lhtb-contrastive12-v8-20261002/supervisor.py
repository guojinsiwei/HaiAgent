"""Side-by-side supervision, leaving frozen methods, trial budgets and results intact."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

VERSION = 'supervision-v3'
TERMINAL = {'completed', 'completed_with_errors', 'needs_attention'}


def scoped_trials(wanted, manifest, scope):
    stage = scope.get('stage', 'pilot')
    if stage in {'pilot', 'pilot_plus3'}:
        indices = scope.get('task_indices', [1, 5])
        expected = 2 if stage == 'pilot' else 5
        if (len(indices) != expected or len(set(indices)) != expected
                or not all(type(i) is int and 0 <= i < len(manifest['tasks']) for i in indices)
                or indices[:2] != [1, 5]):
            raise ValueError('Invalid paired task scope')
        selected = {manifest['tasks'][i]['task']: n for n, i in enumerate(indices)}
        wanted = [(name, spec) for name, spec in wanted
                  if spec['task']['task'] in selected and spec['method'].endswith('1')]
        wanted.sort(key=lambda item: selected[item[1]['task']['task']])
    elif stage != 'screen':
        raise ValueError('Unknown experiment stage')
    return wanted


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write(path, value):
    temp = path.with_name(path.name + '.v2.tmp')
    with temp.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[19] if fields[0] != 'Z' else None
    except (OSError, IndexError):
        return None


def disposition(row, events):
    """Scientific failure is recorded independently from permission to dispatch."""
    reasons = list((row.get('classification') or {}).get('reasons', []))
    method_issues = list((row.get('classification') or {}).get('method_issues', []))
    errors = [i for i, e in enumerate(events) if e.get('event') == 'model_error']
    recovered = sum(e.get('role') == 'memory' and any(
        later.get('event') == 'model_response' for later in events[i+1:])
        for i, e in enumerate(events) if e.get('event') == 'model_error')
    endings = [e for e in events if e.get('event') == 'method_end']
    end = endings[-1] if endings else {}
    stop = end.get('stop_reason') or (end.get('result') or {}).get('stop_reason') or row.get('stop_reason')
    # Only explicit diagnostic evidence can classify a shared credential failure.
    fatal_codes = {'http_401', 'http_402', 'http_403', 'provider_401', 'provider_402', 'provider_403'}
    fatal = any(str(e.get('error_code', '')) in fatal_codes
                for e in events if e.get('event') in {'api_end', 'model_error'} and e.get('role') != 'monitor')
    recovered_only = bool(errors) and recovered == len(errors) and stop in {
        'wall_budget', 'wall_budget_exhausted', 'model_submit', 'submit'}
    effective_method = [r for r in method_issues if not (r == 'model_error' and recovered_only)]
    infrastructure_failure = bool(reasons or row.get('infrastructure_error') or row.get('needs_attention'))
    failure = bool(infrastructure_failure or effective_method)
    return {'stop_reason': stop, 'auxiliary_errors_recovered': recovered,
            'model_errors_recovered': (row.get('classification') or {}).get('recovered_model_errors', 0),
            'optional_monitor_errors': (row.get('classification') or {}).get('optional_monitor_errors', 0),
            'trial_failure': failure, 'admission_failure': infrastructure_failure,
            'blocks_dispatch': fatal, 'reasons': reasons,
            'method_issues': effective_method,
            'original_reasons': reasons, 'original_method_issues': method_issues}


def failure_streak(rows):
    streak = 0
    for row in reversed(rows):
        if not row['supervision']['admission_failure']:
            break
        streak += 1
    return streak


class Supervisor:
    def __init__(self, root, kind):
        self.root, self.kind = Path(root).resolve(), kind
        sys.path[:0] = [str(self.root), str(self.root/'runtime/src'),
                       str(self.root/'hai-project/src'), str(self.root/'bestfgs-project/src'),
                       str(self.root/'upstream/harbor/src')]
        import control
        self.control = control
        self.ready = control.validate()
        self.ledger = self.root/'ledger'
        self.ledger.mkdir(exist_ok=True)
        self.children = []
        self.cache = {}
        self.supervisor_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if kind == 'college':
            manifest = read(self.root/'manifest.json')
            self.prior = read(self.root/'prior-results.json', [])
            self.wanted = []
            prior = {(r['task'], r['method']) for r in self.prior}
            for index, task in enumerate(manifest['tasks']):
                methods = control.METHODS[index % len(control.METHODS):] + control.METHODS[:index % len(control.METHODS)]
                for method in methods:
                    if (task['task'], method) not in prior:
                        self.wanted.append((method+'-'+task['task'], {'task': task, 'method': method}))
            self.total, self.slots = manifest['total_trials'], control.PARALLEL_SLOTS
            scope=read(self.root/'run-scope.json',{'stage':'pilot'})
            self.wanted = scoped_trials(self.wanted, manifest, scope)
            self.total = len(self.prior) + len(self.wanted)
            self.slots = scope.get('parallel_slots', self.slots)
            if type(self.slots) is not int or not 1 <= self.slots <= 8:
                raise ValueError('Invalid parallel slot count')
            from resources import fits
            if any(not fits([spec['task']] * self.slots, cpu_cap=32,
                            memory_cap_mb=64 * 1024, max_slots=8) for _, spec in self.wanted):
                raise ValueError('Parallel reservations exceed campaign cap')
            self.disk_guard_enabled = not scope.get('disable_disk_guard', False)
            if type(scope.get('disable_disk_guard', False)) is not bool:
                raise ValueError('Invalid disk policy')
            self.stage=scope['stage']
        else:
            self.prior = []
            self.wanted = [(task, {'task': task}) for task in self.ready['tasks']]
            self.total, self.slots = len(self.wanted), 1
            self.disk_guard_enabled = True

    def event(self, name, **fields):
        with (self.root/'supervision-v2.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(event=name, time=time.time(), **fields))+'\n')
            stream.flush()
            os.fsync(stream.fileno())

    def collect(self):
        rows, active, blockers = [], [], []
        expected = {name for name, _ in self.wanted}
        if any(p.is_dir() and p.name not in expected for p in self.ledger.iterdir()):
            raise RuntimeError('unexpected_ledger_job')
        for folder in sorted(self.ledger.iterdir(), key=lambda p: (p/'result.json').stat().st_mtime if (p/'result.json').exists() else 0):
            if not folder.is_dir():
                continue
            result = folder/'result.json'
            if result.exists():
                signature = (result.stat().st_mtime_ns, result.stat().st_size)
                if self.cache.get(folder.name, (None,))[0] != signature:
                    row = read(result)
                    events = []
                    if row.get('report'):
                        audit = Path(row['report']).parent/'agent/audit.jsonl'
                        events = [json.loads(line) for line in audit.read_text().splitlines()]
                    elif self.kind == 'cube':
                        audit = self.root/'runs'/folder.name/'events.jsonl'
                        if audit.exists():
                            events = [json.loads(line) for line in audit.read_text().splitlines()]
                    row['supervision'] = disposition(row, events)
                    self.cache[folder.name] = signature, row
                row = self.cache[folder.name][1]
                rows.append(row)
                if row['supervision']['blocks_dispatch']:
                    blockers.append({'job': folder.name, 'reason': 'credential_or_balance_error'})
                continue
            intent = read(folder/'intent.json', {})
            start = read(folder/'started.json')
            deadline_stop = read(folder/'deadline-stop.json')
            if deadline_stop and deadline_stop.get('error'):
                blockers.append({'job': folder.name, 'reason': 'deadline_stop_failed',
                                 'error_type': deadline_stop['error']})
            if start and identity(start['pid']) == start['identity']:
                active.append({'job': folder.name, **intent, 'pid': start['pid']})
            elif time.time()-intent.get('created', 0) < 60:
                active.append({'job': folder.name, **intent})
            else:
                blockers.append({'job': folder.name, 'reason': 'child_missing_no_replay'})
        if failure_streak(rows) >= 3:
            blockers.append({'reason': 'three_consecutive_trial_infrastructure_failures'})
        return rows, active, blockers

    def disk_ok(self):
        import shutil
        # Admission stops well before the frozen executor's 60 GiB hard floor,
        # leaving room for up to three already running trials to finish.
        paths, default = ([self.root, Path('/var/lib/docker')], 120) if self.kind == 'college' else ([self.root], 4)
        limit = self.ready.get('disk_reserve_gib', default)
        if type(limit) not in (int, float) or limit <= 0:
            raise RuntimeError('invalid_disk_reserve')
        free = {str(p): round(shutil.disk_usage(p).free / 2**30, 2) for p in paths}
        return not self.disk_guard_enabled or min(free.values()) >= limit, free

    def trial_timeout_seconds(self, spec):
        """Persistent outer deadline, separate from a method's scientific budget."""
        if self.kind == 'college':
            task = spec.get('task') or {}
            agent = float((task.get('agent') or {}).get('timeout_sec', 0))
            verifier = float((task.get('verifier') or {}).get('timeout_sec', 0))
            if agent <= 0 or verifier < 0:
                raise RuntimeError('invalid_trial_timeout')
            # control.execute allows agent + verifier + 900 seconds.  Give the
            # independent worker one final minute to persist its report.
            return agent + verifier + 960
        value = self.ready.get('trial_hard_seconds', 7200)
        if type(value) not in (int, float) or value <= 0:
            raise RuntimeError('invalid_trial_timeout')
        return float(value)

    def enforce_deadlines(self):
        """Stop an owned over-deadline process group once; never replay its trial."""
        now = time.time()
        for folder in self.ledger.iterdir():
            if not folder.is_dir() or (folder/'result.json').exists():
                continue
            intent = read(folder/'intent.json', {})
            deadline = intent.get('hard_deadline_at')
            if type(deadline) not in (int, float) or now <= deadline:
                continue
            started = read(folder/'started.json')
            marker = read(folder/'deadline-stop.json')
            alive = bool(started and identity(started.get('pid')) == started.get('identity'))
            if alive:
                if marker is None:
                    try:
                        os.killpg(started['pid'], signal.SIGTERM)
                        marker = {'requested_at': now, 'signal': 'SIGTERM',
                                  'pid': started['pid'], 'identity': started['identity']}
                        write(folder/'deadline-stop.json', marker)
                        self.event('trial_deadline_stop', job=folder.name, signal='SIGTERM')
                    except OSError as error:
                        write(folder/'deadline-stop.json', {'requested_at': now,
                            'pid': started['pid'], 'identity': started['identity'],
                            'error': type(error).__name__})
                    continue
                if marker.get('error'):
                    continue
                if now - marker.get('requested_at', now) > 30:
                    try:
                        os.killpg(started['pid'], signal.SIGKILL)
                        write(folder/'deadline-stop.json', marker | {'kill_requested_at': now,
                                                                     'signal': 'SIGKILL'})
                        self.event('trial_deadline_stop', job=folder.name, signal='SIGKILL')
                    except OSError as error:
                        write(folder/'deadline-stop.json', marker | {'error': type(error).__name__})
                continue
            # The exact launched attempt is terminal after the owned process exits.
            # Record an infrastructure outcome and continue the queue without replay.
            if marker is not None or started is None:
                value = {'infrastructure_error': 'trial_hard_deadline_exceeded',
                         'needs_attention': True, 'stop_reason': 'outer_trial_deadline',
                         'classification': {'infrastructure_ok': False,
                                            'reasons': ['trial_hard_deadline_exceeded']}}
                if self.kind == 'college':
                    value.update(task=(intent.get('task') or {}).get('task'),
                                 method=intent.get('method'))
                else:
                    value.update(task_id=intent.get('task'))
                write(folder/'result.json', value)
                self.event('trial_deadline_recorded', job=folder.name)

    def scheduler(self, key):
        with (self.root/'worker.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.environ['DEEPSEEK_API_KEY'] = key
            if not self.disk_guard_enabled:
                os.environ['LHTB_DISABLE_DISK_GUARD'] = '1'
            else:
                os.environ.pop('LHTB_DISABLE_DISK_GUARD', None)
            state_before = None
            while True:
                for child in self.children:
                    child.poll()
                self.enforce_deadlines()
                rows, active, blockers = self.collect()
                pending = [(n, s) for n, s in self.wanted if not (self.ledger/n).exists()]
                disk_ok, free = self.disk_ok()
                while pending and len(active) < self.slots and disk_ok and not blockers:
                    self.control.validate()
                    name, spec = pending.pop(0)
                    folder = self.ledger/name
                    folder.mkdir()
                    created = time.time()
                    spec = dict(spec, created=created)
                    spec['hard_deadline_at'] = created + self.trial_timeout_seconds(spec)
                    write(folder/'intent.json', spec)
                    executable = self.control.PYTHON if self.kind == 'college' else sys.executable
                    script = self.root/('durable.py' if self.kind == 'college' else 'supervise.py')
                    env = self.control.environment(spec['method']) if self.kind == 'college' else dict(os.environ)
                    with (folder/'worker.log').open('x') as log:
                        child = subprocess.Popen([executable, '-B', str(script), 'trial', name],
                            cwd=self.root, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    self.children.append(child)
                    active.append(dict(spec, job=name, pid=child.pid))
                    self.event('dispatch', job=name, pid=child.pid)
                    disk_ok, free = self.disk_ok()
                issues = [{'job': r.get('method', '')+'-'+r.get('task', r.get('task_id', '')),
                           **r['supervision']} for r in rows if r['supervision']['trial_failure'] or r['supervision']['auxiliary_errors_recovered'] or r['supervision'].get('model_errors_recovered') or r['supervision'].get('optional_monitor_errors')]
                for running in active:
                    pattern = running['job']+'/*/agent/audit.jsonl' if self.kind == 'college' else running['job']+'/events.jsonl'
                    audits = list((self.root/'runs').glob(pattern))
                    if audits:
                        running['audit_age_seconds'] = round(time.time()-max(p.stat().st_mtime for p in audits), 1)
                        running['log_stale'] = running['audit_age_seconds'] > 1800
                prior_errors = [r for r in self.prior if r.get('infrastructure_error') or r.get('recovery_action')]
                state = ('draining_after_error' if active else 'needs_attention') if blockers else (
                    ('completed_with_errors' if prior_errors or any(r['supervision']['trial_failure'] for r in rows) else 'completed')
                    if not pending and not active else 'waiting_for_disk' if not disk_ok and pending else 'running')
                if state != state_before:
                    self.event('state', state=state, blockers=blockers)
                    state_before = state
                health = dict(state=state, updated=time.time(), total=self.total,
                    completed=len(self.prior)+len(rows), pending=len(pending), active=active,
                    problems=blockers, trial_issues=issues, free_gib=free, supervision_version=VERSION,
                    carried_failures=len(prior_errors), supervisor_sha256=self.supervisor_sha256,
                    official_reports=sum(r.get('verifier_result') is not None for r in self.prior+rows),
                    protocol_sha256=self.ready.get('protocol_sha256'))
                health.update(stage=self.stage,screen_total=self.total,parallel_slots=self.slots,
                              disk_guard_enabled=self.disk_guard_enabled)
                write(self.root/'summary-v2.json', self.prior+rows)
                write(self.root/'summary.json', self.prior+rows)
                write(self.root/'health.json', health)
                if state in TERMINAL:
                    return
                time.sleep(15)


def guard(root, kind, key):
    root = Path(root).resolve()
    with (root/'guard.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        failures = 0
        try:
            while failures < 4:
                start = time.time()
                child = subprocess.Popen([sys.executable, '-B', __file__, 'scheduler', str(root), kind, '--key-stdin'],
                                         cwd=root, stdin=subprocess.PIPE, start_new_session=True)
                child.stdin.write((key+'\n').encode())
                child.stdin.close()
                while child.poll() is None:
                    time.sleep(5)
                    health = read(root/'health.json', {})
                    age = time.time()-max(start, health.get('updated', 0))
                    write(root/'guard-health.json', dict(updated=time.time(), scheduler_pid=child.pid,
                        scheduler_heartbeat_age=age, consecutive_restarts=failures, supervision_version=VERSION))
                    if age > 180:
                        child.terminate()
                        try: child.wait(timeout=10)
                        except subprocess.TimeoutExpired: child.kill(); child.wait()
                health = read(root/'health.json', {})
                if child.returncode == 0 and health.get('state') in TERMINAL:
                    write(root/'guard-health.json', dict(updated=time.time(), state=health['state'],
                        supervision_version=VERSION, scheduler_exit_code=child.returncode))
                    return
                failures = 1 if time.time()-start > 300 else failures+1
                write(root/'guard-failure.json', dict(updated=time.time(), reason='scheduler_exit',
                    exit_code=child.returncode, consecutive_restarts=failures))
                if failures < 4:
                    time.sleep(min(60, 5 * 2**failures))
            write(root/'health.json', dict(state='needs_attention', updated=time.time(),
                reason='scheduler_restart_limit', supervision_version=VERSION))
        finally:
            # Credential remains only in process memory/anonymous pipes.
            key = None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['scheduler', 'guard', 'inspect'])
    parser.add_argument('root')
    parser.add_argument('kind', choices=['college', 'cube'])
    parser.add_argument('--key-stdin', action='store_true')
    args = parser.parse_args()
    key = None
    if args.mode != 'inspect':
        if not args.key_stdin:
            raise ValueError('Secret must arrive through protected stdin')
        key = sys.stdin.readline().strip()
        if not key or len(key) > 1024 or any(c.isspace() for c in key):
            raise ValueError('Invalid protected input')
    if args.mode == 'guard':
        guard(args.root, args.kind, key)
    else:
        supervisor = Supervisor(args.root, args.kind)
        if args.mode == 'inspect':
            rows, active, blockers = supervisor.collect()
            print(json.dumps(dict(completed=len(supervisor.prior)+len(rows), active=active, blockers=blockers,
                                  dispositions=[r['supervision'] for r in rows])))
        else:
            supervisor.scheduler(key)
