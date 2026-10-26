"""Score frozen FEAL filesystem with original tests, resources, and deadline."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import tomllib
from types import SimpleNamespace
from storage import atomic_json
from verifier_setup import prepare_verifier, verifier_network, validate_test_report
from repair_hooks import handoff_verifier_logs

R = Path(__file__).resolve().parent
ORIGINAL = R.parent / 'tb2-hld-recuris39-20261021'
JOB = 'tb2hr39-13-recuris-feal-linear-cryptanalysis'
NAME = 'tb2hr39-feal-score-repair4'
A = R / 'feal-score'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calls():
    with sqlite3.connect('file:' + str(ORIGINAL / 'spending.sqlite') + '?mode=ro', uri=True) as db:
        return db.execute('SELECT count(*) FROM calls WHERE job=?', (JOB,)).fetchone()[0]


class Environment:
    async def upload_file(self, source, target):
        subprocess.run(['docker', 'cp', str(source), NAME + ':' + target],
                       check=True, capture_output=True, timeout=120)

    async def exec(self, command, user='root', env=None, timeout_sec=900):
        args = ['docker', 'exec', '-u', user]
        for k, v in (env or {}).items():
            args += ['-e', k + '=' + str(v)]
        result = subprocess.run(args + [NAME, 'bash', '-c', command],
                                capture_output=True, text=True, timeout=timeout_sec)
        return SimpleNamespace(return_code=result.returncode, stdout=result.stdout, stderr=result.stderr)


async def main():
    A.mkdir(exist_ok=False)
    trial = next((ORIGINAL / 'jobs' / JOB).glob('*/submission-snapshot.json')).parent
    snapshot = json.loads((trial / 'submission-snapshot.json').read_text())
    task = R / 'dependencies/official/tasks/feal-linear-cryptanalysis'
    config = tomllib.loads((task / 'task.toml').read_text())
    assert config['environment']['cpus'] == 1 and config['environment']['memory'] == '2G'
    test_hashes = {str(p.relative_to(task / 'tests')): digest(p)
                   for p in (task / 'tests').rglob('*') if p.is_file()}
    tests = A / 'tests'
    shutil.copytree(task / 'tests', tests)
    output = A / 'verifier'
    output.mkdir()
    before = calls()
    result = dict(source_trial=str(trial), snapshot=snapshot, original_result_sha256=digest(trial / 'result.json'),
                  official_test_hashes=test_hashes, solver_rerun=False, paid_calls=0,
                  original_calls_before=before, cpu_limit=1, memory_gib=2,
                  timeout_seconds=config['verifier']['timeout_sec'])
    atomic_json(A / 'provenance.json', result)
    subprocess.run(['docker', 'run', '-d', '--name', NAME, '--label', 'experiment=' + R.name,
                    '--cpus', '1', '--memory', '2g', '--network', 'bridge', '--user', 'root',
                    '--entrypoint', 'sleep', '--mount', f'type=bind,src={tests},dst=/tests',
                    '--mount', f'type=bind,src={output},dst=/logs/verifier',
                    snapshot['image_id'], 'infinity'], check=True, capture_output=True, timeout=60)
    verifier = SimpleNamespace(task=SimpleNamespace(paths=SimpleNamespace(task_dir=task)),
                               trial_paths=SimpleNamespace(verifier_dir=output),
                               environment=Environment(), verifier_env={})
    started = time.time()
    try:
        atomic_json(A / 'health.json', dict(state='preparing', updated=time.time(), paid_calls=0))
        with verifier_network(verifier):
            await prepare_verifier(verifier)
            atomic_json(A / 'health.json', dict(state='verifying', updated=time.time(), paid_calls=0))
            scored = await verifier.environment.exec('bash /tests/test.sh', env=verifier.verifier_env,
                           timeout_sec=config['verifier']['timeout_sec'])
            (output / 'test-stdout.txt').write_text(scored.stdout)
            (output / 'test-stderr.txt').write_text(scored.stderr)
            await handoff_verifier_logs(verifier.environment, verifier.environment.exec)
            validate_test_report(verifier)
            reward = int((output / 'reward.txt').read_text().strip())
            assert reward in (0, 1)
            result.update(engineering_clean=True, reward=reward,
                          tests=json.loads((output / 'ctrf.json').read_text())['results']['summary'],
                          exit_code=scored.return_code)
    except Exception as error:
        result.update(engineering_clean=False, reward=None, error_type=type(error).__name__, error=str(error)[:500])
    finally:
        subprocess.run(['docker', 'stop', '-t', '2', NAME], capture_output=True, timeout=30)
        result.update(elapsed_seconds=time.time()-started, original_calls_after=calls())
        result['paid_calls'] = result['original_calls_after'] - before
        result['original_result_unchanged'] = digest(trial / 'result.json') == result['original_result_sha256']
        result['official_tests_unchanged'] = all(digest(task / 'tests' / k) == v and digest(tests / k) == v
                                                 for k, v in test_hashes.items())
        assert result['paid_calls'] == 0 and result['original_result_unchanged'] and result['official_tests_unchanged']
        atomic_json(A / 'result.json', result)
        atomic_json(A / 'health.json', dict(state='finished', updated=time.time(), result=result))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
