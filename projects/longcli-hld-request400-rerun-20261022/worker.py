"""Five explicitly authorized fresh attempts, with no automatic paid retries."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib, json, os, subprocess, sys, time

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / 'longcli-hld-full20-triple-20261022'
PREFIX = 'hld-request400'

def read(p): return json.loads(p.read_text())

def validate():
    proof = read(ROOT/'preflight.json')
    assert proof['passed']
    for name, digest in proof['hashes'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name

def scoped(path):
    from spending import Ledger
    profile = read(PARENT/'budget-profile.json')
    ledger = Ledger(path, profile)
    ledger.profile = {**profile, 'jobs': [PREFIX+'--'+r['task'] for r in read(ROOT/'protocol.json')['tasks']],
                      'requests_per_task':800, 'max_output_tokens':32768}
    return ledger

def run():
    validate()
    from common import save
    from runner import solve
    ledger = scoped(PARENT/'spending.sqlite')
    assert ledger.status()['remaining_microcny'] >= 120000000
    secret = read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')
    key = secret.get('key') or secret.get('api_key') or secret.get('apiKey')
    assert key
    tasks = read(ROOT/'protocol.json')['tasks']
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(solve, row, key, ledger): row['task'] for row in tasks}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                results.append(dict(task=futures[future], state='needs_attention', error=str(e).replace(key,'[REDACTED]')[:500]))
            save(ROOT/'summary.json', dict(completed=results, updated=time.time(), budget=ledger.status()))

if __name__ == '__main__':
    if '--run' in sys.argv:
        run()
    else:
        validate()
        assert (ROOT/'entry-probe.json').exists(), 'Zero-model entry probe required'
        with (ROOT/'launch-once.marker').open('x') as f:
            f.write('HLD v8, P0/P2/Pgtbl/Syscall/Traps; 800 requests, 32768 output, 128K context, 24 CNY/task; original 480 CNY ledger\n')
        with (ROOT/'supervisor.log').open('ab', buffering=0) as log:
            proc = subprocess.Popen([sys.executable, __file__, '--run'], stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=log, start_new_session=True)
        receipt = dict(pid=proc.pid, started=time.time(), tasks=[r['task'] for r in read(ROOT/'protocol.json')['tasks']],
                       concurrency=3, task_budget_cny=24, shared_campaign_budget_cny=480,
                       fresh_attempts=True, no_hints=True, auto_retries=False)
        (ROOT/'launch-receipt.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt))
