"""Bounded zero-model portability checks in a new, task-only directory."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import time
ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'inputs'
def manifest():
    rows = {}
    for p in SOURCE.rglob('*'):
        if p.is_symlink():
            rows[str(p.relative_to(SOURCE))] = 'symlink:' + os.readlink(p)
        elif p.is_file():
            h = hashlib.sha256()
            with p.open('rb') as f:
                for b in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(b)
            rows[str(p.relative_to(SOURCE))] = h.hexdigest()
    return rows
before = manifest()
rows = []
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
def run(name, argv, cwd, timeout=180):
    start = time.time()
    with (ROOT / (name + '.log')).open('w') as log:
        try:
            p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            p.wait(timeout=timeout)
            code, timed_out = p.returncode, False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            code, timed_out = None, True
    row = dict(check=name, exit_code=code, timeout=timed_out, elapsed=time.time()-start)
    rows.append(row)
    print(json.dumps(row), flush=True)
    return code == 0
run('scheme-help', ['python3', '-B', 'scheme.py', '--help'], SOURCE / 'cs61_fa24_scheme')
cmake = ROOT / 'runtime2/bin/cmake'
if run('cpp-configure', [str(cmake), '-S', str(SOURCE / 'cmu15_445'), '-B', str(ROOT / 'cpp-build'),
                         '-DCMAKE_BUILD_TYPE=Debug'], ROOT):
    run('cpp-primer-build', [str(cmake), '--build', str(ROOT / 'cpp-build'), '--target', 'bustub_primer', '-j2'], ROOT, 300)
after = manifest()
result = {'model_calls': 0, 'checks': rows, 'source_unchanged': before == after,
          'files': len(before), 'manifest': before}
(ROOT / 'cube-result.json').write_text(json.dumps(result, indent=2))
if before != after:
    raise RuntimeError('Smoke check mutated source; no submission packaged')
subprocess.run(['tar', '-czf', str(ROOT / 'returned-source.tar.gz'), '-C', str(SOURCE),
                'cs61_fa24_scheme', 'cmu15_445'], check=True)
print(json.dumps({'packaged': True, 'source_unchanged': True}), flush=True)
