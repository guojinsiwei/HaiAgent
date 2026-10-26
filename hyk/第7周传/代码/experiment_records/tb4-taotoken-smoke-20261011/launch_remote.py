"""Local hidden input reaches this launcher over SSH stdin, not argv."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
os.chdir(root)
def status(state, **more):
    (root / 'status.json').write_text(json.dumps(dict(state=state,
        updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), **more), indent=2))

if '--supervise' not in sys.argv:
    if not (root / 'preflight.ok').exists():
        raise SystemExit('Preflight has not passed; refusing paid execution')
    key = sys.stdin.readline(8192).strip()
    if not key or len(key) > 8000:
        raise SystemExit('Missing credential')
    marker = root / 'launch-once.marker'
    with marker.open('x') as f:
        f.write('One authorized trial; no automatic retry.\n')
    env = dict(os.environ, TAOTOKEN_API_KEY=key, PYTHONPATH=str(root))
    with (root / 'supervisor.log').open('ab', buffering=0) as log:
        child = subprocess.Popen([str(root / 'venv/bin/python'), __file__, '--supervise'],
            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    print(json.dumps({'started': True, 'supervisor_pid': child.pid}))
else:
    status('running', supervisor_pid=os.getpid(), job='taotoken-smoke')
    command = [str(root / 'venv/bin/harbor'), 'run', '-p',
        'task-transport/wal-recovery-ordering', '-a', 'harbor_kz:KZInstalledAgent',
        '--env', 'docker', '--no-delete', '-n', '1', '-k', '1', '-r', '0',
        '--agent-timeout-multiplier', '0.07', '--job-name', 'taotoken-smoke', '-o', str(root / 'jobs')]
    code = subprocess.call(command, stdin=subprocess.DEVNULL)
    results = list((root / 'jobs/taotoken-smoke').glob('*/result.json'))
    outcome = json.loads(results[0].read_text()) if len(results) == 1 else {}
    error = outcome.get('exception_info')
    status('failed' if code or error or not results else 'finished', exit_code=code,
           result_files=[str(p.relative_to(root)) for p in results],
           exception_type=error.get('exception_type') if isinstance(error, dict) else None,
           verifier_result=outcome.get('verifier_result'))
