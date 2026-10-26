"""Finite authorized repair batch; no scheduled AI task, no ledger reset."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from campaign import trial, proxy_module
from queue_policy import TERMINAL, finish, summary
from recovery import process_identity, owned_alive
from spending import BudgetService
from storage import atomic_json, supervisor_lock

R = Path(__file__).resolve().parent
ORIGINAL = R.parent / 'tb2-hld-recuris39-20261021'
OTHER = R.parent / 'tb2-hld-recuris39-repair4-20261021'
PY = str(R / 'venv/bin/python')


def read(path):
    return json.loads(path.read_text())


def frozen_results_intact():
    return all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
               for p, digest in read(R / 'preserved-results.json').items())


def rows_to_retry():
    return [dict(task=r['task'], arm=r['arm'], stage='retry', state='pending',
                 job=r['job']+'-repair5', budget_job=r['job'], original_job=r['job'])
            for r in read(R / 'original-failures.json')
            if r['task'] == 'polyglot-rust-c' and r['arm'] == 'hld']


def command(row, offline):
    agent = ('Offline' if offline else '') + ('HLD' if row['arm'] == 'hld' else 'Recuris')
    return [PY, str(R / 'trial_runner.py'), PY, str(R / 'repair_entry.py'),
            'run', '-p', str(R / 'dependencies/official/tasks' / row['task']),
            '-a', 'agents:' + agent, '--env', 'docker', '--no-delete', '-n', '1',
            '-k', '1', '-r', '0', '--verifier-timeout-multiplier', '1',
            '--job-name', ('preflight-' if offline else '') + row['job'],
            '-o', str(R / ('preflight' if offline else 'jobs'))]


def base_env(row, offline):
    env = {k:v for k,v in os.environ.items()
           if not any(x in k for x in ('API_KEY', 'AUTH_TOKEN', 'CAMPAIGN_BUDGET'))}
    env.update(PYTHONPATH=str(R)+':'+str(R/'dependencies'), PYTHONDONTWRITEBYTECODE='1',
               PAIRED_TASK=row['task'], PAIRED_ATTEMPT_ID=row['preflight_attempt_id' if offline else 'attempt_id'],
               PAIRED_PROXY_URL='http://10.123.0.1:29231')
    return env


def preflight():
    with (R / 'preflight-once.marker').open('x') as f:
        f.write(str(time.time()))
    rows = rows_to_retry()
    for row in rows:
        row['preflight_attempt_id'] = uuid.uuid4().hex
        row.update(state='preflighting', admission_offline=True)
        atomic_json(R / 'preflight-status.json', dict(state='running', rows=rows, paid_calls=0))
        with (R / ('preflight-'+row['job']+'.log')).open('x') as log:
            code = subprocess.run(command(row, True), cwd=R, env=base_env(row, True),
                                  stdout=log, stderr=log, stdin=subprocess.DEVNULL).returncode
        result = trial(row, True)
        result['harbor_exit'] = code
        row.update(preflight=result, preflight_ok=code == 0 and result['engineering_clean'])
        row['state'] = 'pending' if row['preflight_ok'] else 'engineering_failure'
        atomic_json(R / 'preflight-status.json', dict(state='running', rows=rows, paid_calls=0))
    result = dict(passed=all(r['preflight_ok'] for r in rows), rows=rows, paid_calls=0,
                  preserved_results_unchanged=frozen_results_intact())
    assert result['preserved_results_unchanged']
    atomic_json(R / 'preflight-acceptance.json', result)
    atomic_json(R / 'preflight-status.json', dict(state='finished', **result))
    print(json.dumps(result), flush=True)


def free_slots(main, other, active_count):
    # Count all remaining main-batch admissions, including preflight-to-paid
    # transitions. The unchanged main supervisor can never refill beyond this.
    remaining = sum(r['state'] not in TERMINAL and r['state'] != 'paused_by_user'
                    for r in main['rows'] + other['rows'])
    return max(0, 8 - min(8, remaining) - active_count)


def supervise():
    acceptance = read(R / 'preflight-acceptance.json')
    assert acceptance['passed'] and acceptance['preserved_results_unchanged']
    assert frozen_results_intact()
    assert read(R / 'budget-profile.json') == read(ORIGINAL / 'budget-profile.json')
    secret = read(Path.home() / '.config/appworld-credentials/taotoken-standby.json')
    key = secret.get('key') or secret.get('api_key') or secret.get('apiKey')
    assert isinstance(key, str) and key.strip()
    rows = acceptance['rows']
    active = {}
    with supervisor_lock(R):
        with (R / 'paid-launch-once.marker').open('x') as f:
            f.write(str(time.time()))
        budget = BudgetService(ORIGINAL, port=29232)
        module = proxy_module()
        proxy = module.ThreadingHTTPServer((module.HOST, 29231), module.Handler)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()

        def checkpoint(state):
            atomic_json(R / 'health.json', dict(state=state, updated=time.time(),
                supervisor_identity=process_identity(os.getpid()), rows=rows, summary=summary(rows),
                active=[dict(job=r['job'], arm=r['arm'], pid=p.pid, offline=False)
                        for r,p,log in active.values()], spending=budget.snapshot(),
                budget_root=str(ORIGINAL), no_gpt_calls=True))

        try:
            while True:
                for job, (row, process, log) in list(active.items()):
                    if process.poll() is None:
                        continue
                    log.close()
                    result = trial(row)
                    result['harbor_exit'] = process.returncode
                    if process.returncode:
                        result['engineering_clean'] = False
                    finish(row, result)
                    del active[job]
                if all(r['state'] in TERMINAL for r in rows) and not active:
                    checkpoint('finished')
                    break
                main = read(ORIGINAL / 'health.json')
                if main['state'] not in ('finished', 'drained') and not owned_alive(main.get('supervisor_identity')):
                    checkpoint('held_main_state_unavailable')
                    time.sleep(15)
                    continue
                other = read(OTHER / 'health.json')
                if other['state'] not in ('finished', 'drained') and not owned_alive(other.get('supervisor_identity')):
                    checkpoint('held_other_repair_state_unavailable')
                    time.sleep(15)
                    continue
                slots = free_slots(main, other, len(active))
                for row in rows:
                    if row['state'] != 'pending' or slots <= 0:
                        continue
                    status = budget.snapshot()
                    if status['halt_reason'] or status['remaining_microcny'] <= 0:
                        continue
                    # Reserve space for every admitted main/repair task plus one
                    # cold image. Do not prune or stop somebody else's work.
                    total_active = len(main.get('active', [])) + len(other.get('active', [])) + len(active) + 1
                    if (shutil.disk_usage('/var/lib/docker').free < (44+10*total_active)*2**30
                            or shutil.disk_usage(R).free < 8*2**30):
                        continue
                    row.update(attempt_id=uuid.uuid4().hex, state='paid_admitted', admission_offline=False)
                    checkpoint('running')
                    env = base_env(row, False)
                    env.update(TAOTOKEN_API_KEY=key, CAMPAIGN_BUDGET_REQUIRED='1',
                        CAMPAIGN_BUDGET_URL=budget.url, CAMPAIGN_BUDGET_TOKEN=budget.token,
                        CAMPAIGN_BUDGET_JOB=row['budget_job'],
                        CAMPAIGN_BUDGET_ARM='dsh' if row['arm']=='recuris' else 'kz')
                    log = (R / (row['job']+'.log')).open('x')
                    process = subprocess.Popen(command(row, False), cwd=R, env=env,
                        stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
                    row.update(state='running', pid=process.pid)
                    active[row['job']] = (row, process, log)
                    slots -= 1
                    checkpoint('running')
                checkpoint('running' if active else 'waiting_for_existing_batch_slots')
                time.sleep(15)
        finally:
            for row, process, log in active.values():
                process.wait()
                log.close()
            proxy.shutdown()
            budget.close()


if __name__ == '__main__':
    if sys.argv[1:] == ['--preflight']:
        preflight()
    elif sys.argv[1:] == ['--supervise']:
        supervise()
    else:
        raise SystemExit('Use --preflight or --supervise')
