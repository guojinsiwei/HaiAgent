"""A fresh encrypted-stdin credential, two fixed roots, no keys persisted."""
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent


def read(p): return json.loads(p.read_text()) if p.exists() else {}
def save(p, value):
    tmp = p.with_suffix(p.suffix + '.tmp'); tmp.write_text(json.dumps(value, indent=2)); tmp.replace(p)


def validate():
    ready = read(ROOT / 'ready.json'); assert ready.get('ready')
    for name, digest in ready['hashes'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    return read(ROOT / 'protocol.json')


def arm_worker(method, key):
    directory = ROOT / method; sys.path.insert(0, str(directory)); os.chdir(directory)
    from worker import worker
    worker(key)


def grade_available():
    p = read(ROOT / 'protocol.json'); errors = []; completed = []
    while True:
        for method in p['methods']:
            arm = ROOT / method
            for row in p['tasks']:
                job = method + '--' + row['task']; result = arm / 'grades' / job / 'result.json'
                if result.exists():
                    if job not in completed: completed.append(job)
                    continue
                if not (arm / 'incoming' / job / 'summary.json').exists(): continue
                save(ROOT / 'grading-health.json', {'state': 'grading', 'job': job,
                     'completed': completed, 'errors': errors, 'updated': time.time()})
                receipt = arm / 'incoming' / job
                if (receipt / 'grading-launch.claim').exists():
                    if not any(e['job'] == job for e in errors): errors.append({'job': job, 'reason': 'claimed_without_result'})
                    continue
                (receipt / 'grading-launch.claim').touch(exist_ok=False)
                with (receipt / 'grader.log').open('x') as out, (receipt / 'grader-stderr.log').open('x') as err:
                    process = subprocess.run([sys.executable, '-B', str(arm / 'grade_one.py'), '--job', job],
                        cwd=arm, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
                scored = read(result)
                if process.returncode or scored.get('grading_state') != 'complete' or not scored.get('grading_container_destroyed'):
                    errors.append({'job': job, 'reason': 'grader_failure'})
                if result.exists(): completed.append(job)
        done = all(read(ROOT / m / 'health.json').get('state') in ('generation_complete', 'needs_attention') for m in p['methods'])
        save(ROOT / 'grading-health.json', {'state': 'complete_for_available_artifacts' if done else 'waiting',
             'completed': completed, 'errors': errors, 'updated': time.time(), 'model_calls': 0})
        if done: return
        time.sleep(5)


def supervisor(key):
    p = validate(); ctx = mp.get_context('fork'); children = {}
    for method in p['methods']:
        child = ctx.Process(target=arm_worker, args=(method, key)); child.start(); children[method] = child
    grader = ctx.Process(target=grade_available); grader.start()
    while any(c.is_alive() for c in children.values()):
        states = {m: read(ROOT / m / 'health.json') for m in p['methods']}
        for method, child in children.items():
            if not child.is_alive() and states[method].get('state') not in ('generation_complete', 'needs_attention'):
                save(ROOT / method / 'health.json', {'state': 'needs_attention', 'controller_exit': child.exitcode,
                     'updated': time.time()})
        save(ROOT / 'health.json', {'state': 'running', 'pid': os.getpid(),
             'active': [job for s in states.values() for job in s.get('active', [])],
             'arms': states, 'updated': time.time()})
        time.sleep(5)
    for child in children.values(): child.join()
    save(ROOT / 'health.json', {'state': 'generation_complete', 'active': [],
         'arms': {m: read(ROOT / m / 'health.json') for m in p['methods']}, 'updated': time.time()})
    grader.join()


def main():
    p = validate()
    if '--check' in sys.argv:
        print(json.dumps({'ready': True, 'trials': 14, 'methods': p['methods'], 'paid_model_calls': 0})); return
    key = sys.stdin.readline().strip(); assert key and not any(c.isspace() for c in key)
    request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(request, timeout=30) as response: models = json.load(response)
    assert any(m['id'] == p['model'] for m in models['data'])
    os.close(os.open(ROOT / 'launch.claim', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    pid = os.fork()
    if pid:
        save(ROOT / 'launch.json', {'pid': pid, 'trials': 14, 'credential': 'fresh stdin; RAM only', 'time': time.time()})
        print(json.dumps({'state': 'started', 'pid': pid, 'trials': 14})); return
    os.setsid()
    with open(os.devnull, 'rb') as f: os.dup2(f.fileno(), 0)
    with (ROOT / 'worker.log').open('x') as f: os.dup2(f.fileno(), 1)
    with (ROOT / 'worker-stderr.log').open('x') as f: os.dup2(f.fileno(), 2)
    try: supervisor(key)
    finally: os._exit(0)


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'state': 'launch_failed', 'error_type': type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
