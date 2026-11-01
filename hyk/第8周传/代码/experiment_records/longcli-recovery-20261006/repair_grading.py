"""Explicit model-free repair queue. Immutable inputs, isolated attempts, scoped cleanup."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import types

ROOTS = [Path('/var/tmp/lizh639-' + name) for name in (
    'longcli-dsh20-byte-context-repair-20261006',
    'longcli-reflexion20-college-20261006',
    'longcli-reflexion-recovery-20261006',
    'longcli-retrac-recovery2-20261007')]
OPERATOR = Path('/var/tmp/lizh639-longcli-scoring-repair-20261007')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2))
    tmp.replace(path)


def publish(root, active=None):
    records={p.parent.name:json.loads(p.read_text()) for area in ('jobs','incoming')
             for p in (root/area).glob('*/summary.json')}
    available={job for job,s in records.items() if s.get('state')=='awaiting_grade' and s.get('task_processes_stopped')}
    reports={p.parent.name:json.loads(p.read_text()) for p in (root/'grades').glob('*/result.json')}
    complete={job for job,s in reports.items() if s.get('grading_state')=='complete'}
    save(root/'grading-health.json',{'state':'grading' if active or available-complete else 'complete_for_available_artifacts',
        'job':active,'updated':time.time(),'scored':len(complete),'available':len(available),
        'missing':sorted(available-complete),'model_calls':0,'repair_queue':str(OPERATOR),'errors':{}})


def halt_old_dispatcher(root):
    receipt = root / 'grading-launch.json'
    if not receipt.exists():
        return
    pid = json.loads(receipt.read_text())['pid']
    cmd = Path(f'/proc/{pid}/cmdline')
    if cmd.exists() and str(root / 'grading_worker.py').encode() in cmd.read_bytes().split(b'\0'):
        assert cmd.stat().st_uid == os.getuid()
        os.kill(pid, signal.SIGTERM)
        time.sleep(.3)
        if cmd.exists() and str(root / 'grading_worker.py').encode() in cmd.read_bytes().split(b'\0'):
            os.kill(pid, signal.SIGKILL)


def one(root, job):
    assert root in ROOTS and '/' not in job
    sys.path.insert(0, str(root))
    # Use a known bounded process utility; no solver import or credential access.
    spec = importlib.util.spec_from_file_location('repair_safe', ROOTS[2] / 'safe_process.py')
    safe = importlib.util.module_from_spec(spec); spec.loader.exec_module(safe)
    from common import sha
    import college_grader as grader
    protocol = json.loads((root / 'protocol.json').read_text())
    assert job in {method + '--' + row['task'] for method in protocol['methods'] for row in protocol['tasks']}
    source = root / 'incoming' / job
    if not (source / 'summary.json').exists():
        source = root / 'jobs' / job
    summary = json.loads((source / 'summary.json').read_text())
    assert summary['state'] == 'awaiting_grade' and summary['task_processes_stopped']
    archive = source / 'final-source.tar.gz'
    assert sha(archive) == summary['artifact']['sha256']
    canonical = root / 'grades' / job / 'result.json'
    if canonical.exists():
        assert json.loads(canonical.read_text())['grading_state'] == 'complete'
        publish(root)
        return
    publish(root,job)
    attempt = root / 'grading-recovery-20261007'
    attempt.mkdir(exist_ok=True)
    for filename in ('protocol.json', 'input-manifest.json'):
        dst = attempt / filename
        if not dst.exists(): shutil.copyfile(root / filename, dst)
        assert sha(dst) == sha(root / filename)
    if not (attempt / 'upstream').exists(): (attempt / 'upstream').symlink_to((root / 'upstream').resolve())
    assert not (attempt / 'grades' / job).exists(), 'Prior repair attempt preserved; manual review required'
    owned = set()
    def docker(*args, check=True, seconds=120):
        if args[0] == 'run':
            assert 'experiment=' + protocol['experiment'] in args
            owned.add(args[args.index('--name') + 1])
            save(attempt / (job + '-container.json'), {'names': sorted(owned), 'job': job})
        result = safe.run_bounded(['docker', *map(str, args)], capture_output=True,
            text=True, encoding='utf-8', errors='replace', timeout=seconds)
        if check and result.returncode: raise RuntimeError('Docker failed: ' + result.stderr[-300:])
        return result
    def grading_docker(*args, **kwargs):
        # Defer cleanup to our outer finally so cleanup cannot suppress a score.
        if args[0] == 'stop' and args[-1] in owned:
            return subprocess.CompletedProcess(args, 0, '', '')
        return docker(*args, **kwargs)
    grader.ROOT = attempt
    grader.docker = grading_docker
    grader.subprocess = types.SimpleNamespace(run=safe.run_bounded, STDOUT=subprocess.STDOUT)
    result = None
    cleanup = []
    try:
        result = grader.grade(job, archive, summary['artifact']['sha256'])
        result.update(grading_attempt_root=str(attempt), paid_model_calls_for_repair=0,
                      original_failed_attempt_retained=True)
        save(attempt / 'grades' / job / 'result.json', result)
        if result['grading_state'] == 'complete': save(canonical, result)
    finally:
        for name in owned:
            try:
                labels = json.loads(docker('inspect', name, '--format', '{{json .Config.Labels}}', seconds=10).stdout)
                assert labels.get('experiment') == protocol['experiment']
                state = json.loads(docker('inspect', name, '--format', '{{json .State}}', seconds=10).stdout)
                if state['Running']: docker('kill', name, check=False, seconds=15)
                assert docker('inspect', name, '--format', '{{.State.Running}}', seconds=10).stdout.strip() == 'false'
                docker('rm', name, seconds=15)
                cleanup.append({'name': name, 'removed': True})
            except Exception as exc: cleanup.append({'name': name, 'removed': False, 'error': type(exc).__name__})
        save(attempt / (job + '-cleanup.json'), cleanup)
        if result is not None:
            result['cleanup'] = cleanup
            save(attempt / 'grades' / job / 'result.json', result)
            if result['grading_state'] == 'complete': save(canonical, result)
    assert result and result['grading_state'] == 'complete', 'Official grading failed; no automatic repeat'
    assert all(row['removed'] for row in cleanup), 'Cleanup unconfirmed; stop queue'
    publish(root)
    print(json.dumps({'job': job, 'f2p': result['f2p'], 'model_calls': 0}), flush=True)


def queue():
    OPERATOR.mkdir(exist_ok=True)
    with (OPERATOR / 'queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for root in ROOTS[1:]: halt_old_dispatcher(root)
        while True:
            pending = []
            for root in ROOTS:
                records = {p.parent.name: p for area in ('jobs', 'incoming')
                    for p in (root / area).glob('*/summary.json')}
                for job, path in sorted(records.items()):
                    s = json.loads(path.read_text())
                    if s.get('state') != 'awaiting_grade' or not s.get('task_processes_stopped'): continue
                    target = root / 'grades' / job / 'result.json'
                    if target.exists():
                        assert json.loads(target.read_text())['grading_state'] == 'complete', 'Existing failed score requires review'
                        continue
                    pending.append((root, job))
            for root, job in pending:
                save(OPERATOR / 'health.json', {'state': 'grading', 'root': str(root), 'job': job,
                    'updated': time.time(), 'model_calls': 0})
                with (OPERATOR / (root.name + '-' + job + '.log')).open('x') as log:
                    # All Docker operations bounded. Outer watchdog is longer than official timeout.
                    p = subprocess.Popen([sys.executable, '-B', __file__, '--root', str(root), '--job', job],
                        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
                    save(OPERATOR / 'child.json', {'pid': p.pid, 'root': str(root), 'job': job})
                    deadline = time.monotonic() + 3600
                    while p.poll() is None:
                        save(OPERATOR / 'health.json', {'state': 'grading', 'root': str(root), 'job': job,
                            'pid': p.pid, 'updated': time.time(), 'model_calls': 0})
                        if time.monotonic() > deadline:
                            os.killpg(p.pid, signal.SIGTERM)
                            raise RuntimeError('Grader watchdog elapsed; stop admissions and retain artifacts')
                        time.sleep(5)
                    assert p.returncode == 0, 'Grading failed; stop admissions, inspect attempt'
            h = json.loads((ROOTS[2] / 'health.json').read_text())
            if not pending and h.get('state') in ('generation_complete', 'needs_attention') and not h.get('active'):
                save(OPERATOR / 'health.json', {'state': 'complete_for_available_artifacts', 'updated': time.time(), 'model_calls': 0})
                return
            time.sleep(5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--root', type=Path); parser.add_argument('--job')
    parser.add_argument('--retrac-repair',action='store_true')
    args = parser.parse_args()
    if args.retrac_repair:OPERATOR=Path('/var/tmp/lizh639-longcli-retrac-scoring-repair-20261007')
    try:
        if args.root:
            with Path('/var/tmp/lizh639-longcli-owned-grader.lock').open('a') as shared:
                fcntl.flock(shared, fcntl.LOCK_EX)
                one(args.root, args.job)
        else: queue()
    except Exception as exc:
        save(OPERATOR / 'health.json', {'state': 'needs_attention', 'updated': time.time(),
            'error_type': type(exc).__name__, 'error': str(exc)[:400], 'model_calls': 0})
        if args.root:
            save(args.root/'grading-health.json',{'state':'needs_attention','job':args.job,
                'updated':time.time(),'error_type':type(exc).__name__,'error':str(exc)[:400],'model_calls':0})
        raise
