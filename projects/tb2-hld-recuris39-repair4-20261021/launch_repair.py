"""Start this finite experiment batch once after successful keyless acceptance."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

R = Path(__file__).resolve().parent
ORIGINAL = R.parent/'tb2-hld-recuris39-20261021'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    acceptance = json.loads((R/'preflight-acceptance.json').read_text())
    assert acceptance['passed'] and acceptance['paid_calls'] == 0
    assert not (R/'paid-launch-once.marker').exists()
    for base in [ORIGINAL, ORIGINAL/'dependencies']:
        for name, expected in json.loads((base/'ready.json').read_text())['files'].items():
            assert sha(base/name) == expected, 'Original sealed source changed: '+name
    source = {p.name:sha(p) for p in R.glob('*.py')}
    source['runtime-final.tar.gz'] = sha(R/'runtime-final.tar.gz')
    source['python-runtime.tar.gz'] = sha(R/'python-runtime.tar.gz')
    (R/'repair-source-lock.json').write_text(json.dumps(source, indent=2))
    env = {k:v for k,v in os.environ.items()
           if not any(x in k for x in ['API_KEY','AUTH_TOKEN','CAMPAIGN_BUDGET'])}
    env.update(PYTHONPATH=str(R)+':'+str(R/'dependencies'), PYTHONDONTWRITEBYTECODE='1')
    with (R/'supervisor.log').open('x') as log:
        process = subprocess.Popen([str(R/'venv/bin/python'), str(R/'repair_driver.py'), '--supervise'],
            cwd=R, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    time.sleep(2)
    assert process.poll() is None, 'Repair worker exited; inspect before retry'
    result = dict(pid=process.pid, finite_trials=3, original_budget_cny=624,
                  per_original_job_limit_cny=8, global_paid_concurrency_limit=8,
                  scoring_only_recovery='feal-linear-cryptanalysis', gpt_calls=0)
    (R/'launch-receipt.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
