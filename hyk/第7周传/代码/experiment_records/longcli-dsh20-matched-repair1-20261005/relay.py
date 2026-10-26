"""Model-free result return and official grading. Never launches solver retries."""
import json
from pathlib import Path
import subprocess
import time
from deploy import ROOT, REMOTE, KEY, PROXY, COLLEGE, cube

ACADEMY = '/var/tmp/lizh639-' + ROOT.name
GRADER_PY = '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'


def download(worker, remote, local):
    subprocess.run(['scp', '-i', KEY, '-P', str((31081, 31121)[worker]), '-o', 'BatchMode=yes', '-o', PROXY,
                    'root@172.16.108.241:' + remote, str(local)], check=True, timeout=600)


def main():
    done = {p.parent.name for p in (ROOT / 'received').glob('*/official-report.json')
            if json.loads(p.read_text())['grading_state'] == 'complete'}
    while True:
        healths = []
        try:
            for worker in (0, 1):
                result = subprocess.run(cube(worker) + ['test ! -f ' + REMOTE + f'/health-{worker}.json || cat ' + REMOTE + f'/health-{worker}.json'],
                                        capture_output=True, text=True, check=True, timeout=45)
                health = json.loads(result.stdout) if result.stdout.strip() else {'state': 'not_started', 'completed': []}
                healths.append(health)
                for row in health.get('completed', []):
                    job = row['job']
                    if job in done or not row.get('artifact'):
                        continue
                    target = ROOT / 'received' / job
                    target.mkdir(parents=True, exist_ok=True)
                    for filename in ('final-source.tar.gz', 'summary.json', 'events.jsonl', 'console.jsonl', 'stderr.log'):
                        download(worker, REMOTE + '/jobs/' + job + '/' + filename, target / filename)
                    subprocess.run(COLLEGE + ['mkdir -p ' + ACADEMY + '/incoming/' + job], check=True, timeout=30)
                    subprocess.run(['scp', '-i', KEY, '-o', 'BatchMode=yes', str(target / 'final-source.tar.gz'),
                                    str(target / 'summary.json'), 'lizh639@172.16.108.236:' + ACADEMY + '/incoming/' + job + '/'],
                                   check=True, timeout=600)
                    result = subprocess.run(COLLEGE + [f'{GRADER_PY} -B {ACADEMY}/grade_one.py --job {job} --start'],
                                            capture_output=True, text=True, timeout=45)
                    if result.returncode:
                        raise RuntimeError('Official grading invocation failed; preserve claim, no regrade')
                    report = json.loads(result.stdout)
                    # Detached server grading survives local network loss. Keep
                    # official grading sequential to match historical resources.
                    deadline = time.monotonic() + 1500
                    while report.get('grading_state') is None and time.monotonic() < deadline:
                        time.sleep(15)
                        result = subprocess.run(COLLEGE + ['test ! -f ' + ACADEMY + '/grades/' + job + '/result.json || cat ' +
                                                         ACADEMY + '/grades/' + job + '/result.json'],
                                                capture_output=True, text=True, timeout=45, check=True)
                        if result.stdout.strip():
                            report = json.loads(result.stdout)
                    if report.get('grading_state') != 'complete':
                        raise RuntimeError('Official grading incomplete: ' + job)
                    (target / 'official-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                    subprocess.run(['scp', '-r', '-i', KEY, '-o', 'BatchMode=yes',
                                    'lizh639@172.16.108.236:' + ACADEMY + '/grades/' + job + '/test_output', str(target)],
                                   check=True, timeout=120)
                    done.add(job)
            snapshot = {'updated': time.time(), 'workers': healths, 'graded': sorted(done), 'paid_model_calls_by_relay': 0}
            (ROOT / 'relay-health.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
            if all(h['state'] in ('generation_complete', 'needs_attention', 'paused') for h in healths):
                if any(h['state'] in ('needs_attention', 'paused') for h in healths):
                    print(json.dumps({'state': 'needs_attention', 'graded': len(done)}), flush=True)
                    return
                if len(done) == 20:
                    print(json.dumps({'state': 'complete', 'graded': 20}), flush=True)
                    return
        except Exception as error:
            print(json.dumps({'state': 'return_wait', 'error_type': type(error).__name__, 'message': str(error)[:200]}), flush=True)
        time.sleep(60)


if __name__ == '__main__':
    main()
