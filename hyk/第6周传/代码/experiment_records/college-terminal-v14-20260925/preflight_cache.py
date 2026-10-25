"""Exercise the verifier-only cache on the exact frozen task images, without a model."""
import argparse
import asyncio
import json
from pathlib import Path
import shlex
import subprocess
import time
import tomllib
from types import SimpleNamespace

from offline_verifier import CACHE, OfflineVerifier, TARGET, sha

ROOT = Path('/mnt/sdb/home/lizh639/terminalbench-v14-setup/experiment')
RECORDS = CACHE.parent / 'preflight'


class DockerAdapter:
    def __init__(self, name):
        self.name = name

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        args = ['docker', 'exec']
        if user:
            args += ['-u', str(user)]
        if cwd:
            args += ['-w', cwd]
        for key, value in (env or {}).items():
            args += ['-e', key + '=' + value]
        args += [self.name, 'bash', '-c', command]
        run = subprocess.run(args, text=True, capture_output=True, timeout=timeout_sec or 300)
        return SimpleNamespace(return_code=run.returncode, stdout=run.stdout, stderr=run.stderr)

    async def upload_file(self, source_path, target_path):
        subprocess.run(['docker', 'cp', str(source_path), self.name + ':' + target_path], check=True, capture_output=True)


async def check(name, manifest):
    task_dir = ROOT / 'pinned-tasks' / name
    config = tomllib.loads((task_dir / 'task.toml').read_text())
    image = config['environment']['docker_image']
    container = 'tb-offline-preflight-' + name
    env = DockerAdapter(container)
    trial_dir = RECORDS / name
    trial_dir.mkdir(parents=True, exist_ok=True)
    result = {'task': name, 'image': image, 'network': 'none', 'model_calls': 0,
              'manifest_sha256': sha(Path(__file__).with_name('offline-cache-manifest.json')),
              'started_at': time.time(), 'passed': False}
    subprocess.run(['docker', 'run', '-d', '--network', 'none', '--name', container,
                    '--entrypoint', 'sh', image, '-c', 'sleep 900'], check=True, capture_output=True)
    try:
        verifier = OfflineVerifier(task=SimpleNamespace(paths=SimpleNamespace(tests_dir=task_dir / 'tests')),
                                   trial_paths=SimpleNamespace(verifier_dir=trial_dir), environment=env)
        await verifier.prepare_dependencies()
        task = manifest['tasks'][name]
        # The same official installer and package requirements; synthetic tests only.
        setup = 'curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh\nsource "$HOME/.local/bin/env"\n'
        requirements = task['requirements']
        if task['native_pip']:
            setup = 'pip install ' + shlex.join(requirements) + '\n'
            pytest = 'pytest'
        else:
            args = ['uvx', '-p', '3.13']
            for index_line in task['indexes']:
                args += shlex.split(index_line)
            for requirement in requirements:
                args += ['-w', requirement]
            pytest = shlex.join(args + ['pytest'])
        command = 'set -e\n' + setup + 'mkdir -p /tmp/tb-offline-smoke\n' + "printf 'def test_dependency_smoke():\n    assert 1 + 1 == 2\n' > /tmp/tb-offline-smoke/test_smoke.py\n" + pytest + ' --ctrf /tmp/tb-offline-smoke/ctrf.json /tmp/tb-offline-smoke/test_smoke.py -q\n'
        run = await env.exec(command, env=verifier.override_env, timeout_sec=700)
        (trial_dir / 'dependency-smoke.log').write_text(run.stdout + run.stderr)
        result.update(return_code=run.return_code)
        if run.return_code != 0:
            result['error_tail'] = (run.stdout + run.stderr)[-1800:]
        else:
            subprocess.run(['docker', 'cp', container + ':/tmp/tb-offline-smoke/ctrf.json', str(trial_dir / 'synthetic-ctrf.json')], check=True, capture_output=True)
            counts = json.loads((trial_dir / 'synthetic-ctrf.json').read_text())['results']['summary']
            result['passed'] = counts['tests'] == 1 and counts['passed'] == 1 and counts['failed'] == 0
            result['synthetic_ctrf_sha256'] = sha(trial_dir / 'synthetic-ctrf.json')
    except Exception as error:
        result['passed'] = False
        result['error'] = str(error)
    finally:
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
    result['finished_at'] = time.time()
    (trial_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--available', action='store_true')
    parser.add_argument('--tasks', nargs='*')
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name('offline-cache-manifest.json').read_text())
    names = args.tasks or list(manifest['tasks'])
    results = []
    for name in names:
        if manifest['tasks'][name]['group'] not in manifest['payloads'] and args.available:
            continue
        prior = RECORDS / name / 'result.json'
        if prior.exists():
            old = json.loads(prior.read_text())
            stamp = RECORDS / name / 'offline-dependencies.json'
            ctrf = RECORDS / name / 'synthetic-ctrf.json'
            if old.get('passed') and not old.get('error') and stamp.exists() and ctrf.exists():
                counts = json.loads(ctrf.read_text())['results']['summary']
                # A manifest changed when new, disjoint groups arrived; compare this task's payloads.
                before = json.loads(stamp.read_text()).get('payload_sha256', {})
                task_group = manifest['tasks'][name]['group']
                groups = ['base'] + ([task_group] if task_group != 'base' else [])
                now = {g: manifest['payloads'][g]['sha256'] for g in groups}
                if before == now and counts['tests'] == 1 and counts['passed'] == 1 and counts['failed'] == 0:
                    results.append(old)
                    continue
        results.append(await check(name, manifest))
    summary = {'tasks_tested': len(results), 'passed': sum(r['passed'] for r in results),
               'required': 36, 'complete': len(results) == 36 and all(r['passed'] for r in results),
               'scope': 'Synthetic pytest/CTRF dependency smoke tests in frozen images, network disabled; not benchmark scores',
               'manifest_sha256': sha(Path(__file__).with_name('offline-cache-manifest.json')),
               'results': results}
    (RECORDS / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'results'}))


if __name__ == '__main__':
    asyncio.run(main())
