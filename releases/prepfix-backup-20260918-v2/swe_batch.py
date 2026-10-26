"""Cube-Studio batch preparation/search/export. No Docker or evaluation answers here."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile
import uuid
from urllib.parse import urlsplit

from benchmark_runtime import atomic_write_json, atomic_write_text, canonical_sha256, implementation_sha256
from benchmark_splits import reject_frozen_overlap
from run_notebook import run_lock, tree_digest

ROOT = Path(__file__).resolve().parent
MODULES = {'django/django': 'django', 'sympy/sympy': 'sympy', 'scikit-learn/scikit-learn': 'sklearn',
           'matplotlib/matplotlib': 'matplotlib', 'pydata/xarray': 'xarray', 'pylint-dev/pylint': 'pylint',
           'pytest-dev/pytest': '_pytest', 'sphinx-doc/sphinx': 'sphinx', 'astropy/astropy': 'astropy'}
SYSTEM_PACKAGES = ['build-essential', 'gfortran', 'pkg-config', 'libfreetype6-dev', 'libpng-dev',
                   'libqhull-dev', 'libmemcached-dev', 'libffi-dev', 'libssl-dev', 'locales', 'git', 'graphviz']


def load_plan(path):
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    unsigned = {k: v for k, v in plan.items() if k != 'plan_sha256'}
    if plan.get('schema_version') != 1 or canonical_sha256(unsigned) != plan.get('plan_sha256'):
        raise ValueError('Invalid plan checksum/schema')
    tasks = plan.get('tasks', [])
    ids = [t['instance_id'] for t in tasks]
    if len(ids) != plan.get('count') or len(ids) != len(set(ids)) or not ids:
        raise ValueError('Invalid task count/duplicate ids')
    for task in tasks:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+', task['instance_id']):
            raise ValueError('Unsafe task id')
        if task['repo'] not in MODULES or not re.fullmatch('[0-9a-f]{40}', task['base_commit']):
            raise ValueError('Unsupported repository or invalid commit')
        if set(task) != {'instance_id', 'repo', 'base_commit', 'version', 'problem_statement', 'recipe'}:
            raise ValueError('Only public task metadata is allowed in a batch plan')
    reject_frozen_overlap(ids, benchmark='swebench', allow_frozen_test_set=False)
    return plan


def checked(command, *, cwd, env=None, log=None, timeout=1800, ok_codes=(0,)):
    """Every installer/search has a bounded lifetime; kill its descendants on interruption."""
    stream = Path(log).open('a', encoding='utf-8') if log else None
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream, stderr=stream,
                               start_new_session=os.name == 'posix')
    try:
        code = process.wait(timeout=timeout)
        if code not in ok_codes:
            raise RuntimeError(f'Command failed ({code}): {command[0]}; log: {log}')
        return code
    finally:
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.wait()
        if stream:
            stream.close()


def git_value(seed, *args):
    return subprocess.run(['git', *args], cwd=seed, check=True, capture_output=True, text=True, timeout=120).stdout.strip()


def environment_yaml(recipe):
    text = recipe.get('cached_environment_yml')
    if not text:
        raise ValueError('Pinned environment snapshot missing; do not guess task dependencies')
    # Preserve upstream pins/channels; only remove container-specific identity/location.
    return '\n'.join(line for line in text.splitlines() if not re.match(r'^(name|prefix):', line)) + '\n'


def safe_preinstall(task):
    """Vetted adapters for this plan. Never execute upstream global apt upgrades."""
    if task['recipe'].get('repo_setup'):
        raise ValueError('Repository-wide setup needs an explicit notebook adapter')
    commands = task['recipe'].get('pre_install', [])
    commands = [c for c in commands if c != 'apt-get update && apt-get install -y graphviz']
    if task['repo'] == 'matplotlib/matplotlib':
        # Use distro development libraries installed once by --install-system-deps.
        return []
    for command in commands:
        if not command.startswith('sed -i ') or not command.endswith((' setup.py', ' pyproject.toml', ' tox.ini')):
            raise ValueError(f'Unreviewed pre-install command for {task["repo"]}')
    return commands


def activate_env(conda, prefix, body):
    script = Path(conda).resolve().parent.parent / 'etc/profile.d/conda.sh'
    return 'set -euo pipefail\nsource ' + shlex.quote(str(script)) + '\nconda activate ' + shlex.quote(str(prefix)) + '\n' + body + '\n'


def prepare_task(task, args):
    task_root = args.root / 'prepared' / task['instance_id']
    task_root.mkdir(parents=True, exist_ok=True)
    ready = task_root / 'ready.json'
    recipe_hash = canonical_sha256(task)
    if ready.exists():
        data = json.loads(ready.read_text())
        seed = Path(data['workspace'])
        if (data['recipe_sha256'] != recipe_hash or not Path(data['task_python']).is_file()
                or git_value(seed, 'rev-parse', 'HEAD') != data['prepared_commit']
                or git_value(seed, 'status', '--porcelain') or tree_digest(seed) != data['seed_sha256']):
            raise ValueError('Prepared workspace was changed; preserve it and use a fresh batch root')
        return data
    log = task_root / 'prepare.log'
    env = dict(os.environ, CONDA_PKGS_DIRS=str(args.root / 'conda-cache'), PIP_DISABLE_PIP_VERSION_CHECK='1')
    yaml_text = environment_yaml(task['recipe'])
    env_hash = hashlib.sha256(yaml_text.encode()).hexdigest()[:20]
    base_root = args.root / 'base-envs'
    base_root.mkdir(parents=True, exist_ok=True)
    marker = base_root / (env_hash + '.ready.json')
    base = Path(json.loads(marker.read_text())['prefix']) if marker.exists() else base_root / (env_hash + '-' + uuid.uuid4().hex[:8])
    if not marker.exists():
        yaml_path = base.parent / (env_hash + '.yml')
        atomic_write_text(yaml_path, yaml_text)
        checked([args.conda, 'env', 'create', '--prefix', str(base), '--file', str(yaml_path)],
                cwd=task_root, env=env, log=log, timeout=args.prepare_timeout)
        atomic_write_json(marker, {'prefix': str(base), 'environment_sha256': hashlib.sha256(yaml_text.encode()).hexdigest()})
    if not (base / 'bin/python').is_file():
        raise ValueError(f'Cached dependency environment is missing: {base}')
    # Retrying a failed preparation uses fresh paths; partial installations are kept for diagnosis.
    work = task_root / ('attempt-' + uuid.uuid4().hex[:12])
    work.mkdir()
    prefix = work / 'env'
    if not (prefix / 'bin/python').is_file():
        if prefix.exists():
            raise ValueError(f'Partial task environment preserved: {prefix}')
        checked([args.conda, 'create', '-y', '--prefix', str(prefix), '--clone', str(base)],
                cwd=task_root, env=env, log=log, timeout=args.prepare_timeout)
    seed = work / 'seed'
    if not seed.exists():
        seed.mkdir()
        checked(['git', 'init'], cwd=seed, log=log)
        checked(['git', 'remote', 'add', 'origin', 'https://github.com/' + task['repo'] + '.git'], cwd=seed, log=log)
    if not (work / 'checkout.ready').exists():
        if git_value(seed, 'status', '--porcelain'):
            raise ValueError('Partial checkout has local changes; refusing to overwrite')
        checked(['git', 'fetch', '--depth', '1', '--no-tags', 'origin', task['base_commit']], cwd=seed, log=log)
        checked(['git', 'checkout', '--detach', 'FETCH_HEAD'], cwd=seed, log=log)
        checked(['git', 'remote', 'remove', 'origin'], cwd=seed, log=log)
        atomic_write_text(work / 'checkout.ready', task['base_commit'])
    preinstall = safe_preinstall(task)
    if task['repo'] == 'matplotlib/matplotlib':
        # Matplotlib's version-specific build config supports system native libraries.
        atomic_write_text(seed / 'mplsetup.cfg', '[libs]\nsystem_freetype = true\nsystem_qhull = true\n')
    install = task['recipe'].get('install', '')
    if not install.startswith(('python -m pip install ', 'python setup.py install')):
        raise ValueError('Unsupported project installation command')
    # Cached deps are pinned. Editable metadata is installed for CLIs/plugins;
    # the runtime prepends each current snapshot's source paths for imports.
    if install.startswith('python -m pip install '):
        install += ' --no-deps --no-build-isolation'
    setup = work / 'install.sh'
    atomic_write_text(setup, activate_env(args.conda, prefix, '\n'.join(preinstall + [install])))
    checked(['bash', str(setup)], cwd=seed, env=env, log=log, timeout=args.prepare_timeout)
    # Local setup edits form their own baseline, so they cannot leak into model.patch.
    checked(['git', 'add', '-A'], cwd=seed, log=log)
    checked(['git', '-c', 'user.name=BestFGS setup', '-c', 'user.email=setup@localhost',
             'commit', '--allow-empty', '-m', 'Record environment preparation baseline'], cwd=seed, log=log)
    task_python = prefix / 'bin/python'
    module = MODULES[task['repo']]
    with tempfile.TemporaryDirectory(prefix='import-check-', dir=task_root) as scratch:
        clone = Path(scratch) / 'snapshot'
        shutil.copytree(seed, clone, symlinks=True)
        probe_env = dict(env, PYTHONPATH=os.pathsep.join((str(clone / 'src'), str(clone))))
        probe = ('import importlib,os; m=importlib.import_module(' + repr(module) + '); '
                 'p=os.path.realpath(m.__file__); root=os.path.realpath(os.getcwd()); '
                 'assert os.path.commonpath([p,root])==root,(p,root); print(p)')
        checked([str(task_python), '-c', probe], cwd=clone, env=probe_env, log=log, timeout=120)
    freeze = subprocess.run([str(task_python), '-m', 'pip', 'freeze'], capture_output=True, text=True, check=True, timeout=60).stdout
    atomic_write_text(task_root / 'pip-freeze.txt', freeze)
    data = {'id': task['instance_id'], 'workspace': str(seed), 'base_commit': task['base_commit'],
            'prepared_commit': git_value(seed, 'rev-parse', 'HEAD'), 'task_python': str(task_python),
            'recipe_sha256': recipe_hash, 'seed_sha256': tree_digest(seed),
            'goal': task['problem_statement'],
            'success_criteria': ['Resolve the reported issue and verify behavior without regressions.'],
            'constraints': ['Use python from PATH; the task runtime is already prepared.',
                            'Only modify task source. Do not modify existing tests.',
                            'Do not read reference patches, evaluation tests, later history, or online solutions.',
                            'Do not install dependencies or alter system services during search.']}
    atomic_write_json(ready, data)
    return data


def artifacts(root, plan, *, model_name='BestFGS-deepseek-flash'):
    states, predictions = [], []
    for task in plan['tasks']:
        identity = task['instance_id']
        state_file = root / 'states' / (identity + '.json')
        state = json.loads(state_file.read_text()) if state_file.exists() else {'id': identity, 'status': 'pending'}
        states.append(state)
        prediction = root / 'search' / identity / 'predictions.jsonl'
        # Include EVERY selected instance. Preparation failures retain empty patches.
        patch = ''
        if state.get('status') in ('completed', 'model_error', 'search_error') and prediction.exists():
            if state.get('predictions_sha256') and hashlib.sha256(prediction.read_bytes()).hexdigest() != state['predictions_sha256']:
                raise ValueError(f'Saved prediction changed: {identity}')
            rows = [json.loads(line) for line in prediction.read_text().splitlines() if line.strip()]
            if len(rows) != 1 or rows[0]['instance_id'] != identity:
                raise ValueError('Per-task prediction identity mismatch')
            patch = rows[0]['model_patch']
        elif state.get('status') == 'completed':
            raise ValueError(f'Completed task prediction missing: {identity}; restore the saved file before continuing')
        predictions.append({'instance_id': identity, 'model_name_or_path': model_name, 'model_patch': patch})
    atomic_write_json(root / 'summary.json', states)
    atomic_write_text(root / 'predictions.jsonl', ''.join(json.dumps(row, ensure_ascii=True) + '\n' for row in predictions))
    return states


def export_bundle(root, plan, *, model_name='BestFGS-deepseek-flash', comparison=None):
    states = artifacts(root, plan, model_name=model_name)
    files = ['predictions.jsonl', 'summary.json', 'batch.json']
    # Compact evidence, no snapshots/environments/secrets or model prompt history.
    for identity in [t['instance_id'] for t in plan['tasks']]:
        for rel in [f'prepared/{identity}/ready.json', f'prepared/{identity}/pip-freeze.txt',
                    f'search/{identity}/{identity}/status.json']:
            if (root / rel).is_file():
                files.append(rel)
    manifest = {'schema_version': 1, 'dataset': plan['dataset'], 'split': plan['split'],
                'plan_sha256': plan['plan_sha256'], 'expected_ids': [t['instance_id'] for t in plan['tasks']],
                'total': len(states), 'terminal': sum(s['status'] in {'completed','prepare_error','search_error','model_error'} for s in states),
                'sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files}}
    if comparison is not None:
        manifest['comparison'] = comparison
    target = root / 'evaluation-bundle.zip'
    temporary = root / 'evaluation-bundle.tmp'
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        for rel in files:
            archive.write(root / rel, rel)
        archive.writestr('bundle.json', json.dumps(manifest, indent=2))
    os.replace(temporary, target)
    return manifest


def search_task(task, prepared, args, extra):
    identity = task['instance_id']
    manifest = args.root / 'manifests' / (identity + '.json')
    atomic_write_json(manifest, {'schema_version': 1, 'benchmark': 'swebench', 'tasks': [prepared]})
    output = args.root / 'search' / identity
    command = [sys.executable, str(ROOT / 'run_notebook.py'), '--task-manifest', str(manifest),
               '--output-root', str(output), '--python', sys.executable, '--task-python', prepared['task_python'],
               '--task-timeout', str(args.task_timeout)]
    if (output / 'notebook-run.json').exists():
        command.append('--resume')
    command += ['--', *extra]
    env = dict(os.environ, BESTFGS_TASK_SOURCE_PATH='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MPLBACKEND='Agg')
    checked(command, cwd=ROOT, env=env, log=args.root / 'runner.log', timeout=args.task_timeout + 300, ok_codes=(0, 2))
    state = json.loads((output / identity / 'status.json').read_text())
    result = json.loads((Path(state['attempt']) / 'agent-result.json').read_text())
    status = 'completed' if state['status'] == 'completed' else 'search_error'
    if result.get('stop_reason') == 'model_unavailable':
        status = 'model_error'
    return {'id': identity, 'status': status,
            'agent_succeeded': result.get('succeeded'), 'stop_reason': result.get('stop_reason'),
            'model_usage': result.get('model_usage', {}), 'tool_calls': result.get('total_tool_calls'),
            'interaction_rounds': result.get('interaction_rounds'),
            'predictions_sha256': hashlib.sha256((output / 'predictions.jsonl').read_bytes()).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('stage', choices=['prepare', 'run', 'status', 'export'])
    parser.add_argument('--plan', type=Path, default=ROOT / 'examples/swe100-plan.json')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--conda', default='/root/miniconda3/bin/conda')
    parser.add_argument('--task-timeout', type=int, default=14400)
    parser.add_argument('--prepare-timeout', type=int, default=3600)
    parser.add_argument('--min-free-gb', type=float, default=20)
    parser.add_argument('--max-iterations', type=int, default=24)
    parser.add_argument('--max-tool-calls', type=int, default=80)
    parser.add_argument('--adaptive-budget', action='store_true', help='Otherwise use identical fixed budgets for all tasks')
    parser.add_argument('--retry-errors', action='store_true', help='Explicitly retry infrastructure errors only; never solved/unsolved tasks')
    parser.add_argument('--install-system-deps', action='store_true')
    args = parser.parse_args(argv)
    if args.task_timeout <= 0 or args.prepare_timeout <= 0 or args.min_free_gb <= 0 or args.max_iterations <= 0 or args.max_tool_calls <= 0:
        raise ValueError('Timeouts and free-space threshold must be positive')
    args.root = args.root.resolve()
    if args.root == Path(args.root.anchor) or args.root == ROOT or args.root in ROOT.parents or ROOT in args.root.parents:
        raise ValueError('Use a dedicated batch root outside the project')
    plan = load_plan(args.plan)
    extra = ['--provider', 'deepseek', '--model', 'deepseek-flash', '--success-judge-mode', 'off',
             '--max-iterations', str(args.max_iterations), '--max-tool-calls', str(args.max_tool_calls), '--budget-multiplier', '1']
    if not args.adaptive_budget:
        extra.append('--no-adaptive-budget')
    endpoint = os.getenv('DEEPSEEK_API_BASE', 'https://api.deepseek.com')
    parts = urlsplit(endpoint)
    if parts.username or parts.query or parts.fragment or parts.scheme != 'https':
        raise ValueError('Use an HTTPS API endpoint without embedded secrets')
    config = {'schema_version': 1, 'plan_sha256': plan['plan_sha256'], 'agent_args': extra,
              'implementation_sha256': implementation_sha256(ROOT), 'task_timeout': args.task_timeout,
              'python': sys.executable, 'conda': args.conda, 'api_base': endpoint,
              'harness_commit_for_preparation': plan['harness_commit'], 'dataset_fingerprint': plan['dataset_fingerprint']}
    if args.stage in {'status', 'export'} and not (args.root / 'batch.json').is_file():
        raise ValueError('No existing batch')
    prior = args.root / 'batch.json'
    if prior.exists() and json.loads(prior.read_text())['plan_sha256'] != plan['plan_sha256']:
        raise ValueError('This root belongs to a different fixed task plan')
    if args.stage == 'status':
        # State writes are atomic. Monitoring must not compete with the runner lock.
        states = []
        for task in plan['tasks']:
            path = args.root / 'states' / (task['instance_id'] + '.json')
            states.append(json.loads(path.read_text()) if path.exists() else {'id': task['instance_id'], 'status': 'pending'})
        print(json.dumps({'total': len(states), 'counts': dict(Counter(s['status'] for s in states)),
                          'active_or_errors': [s for s in states if s['status'] in {'preparing', 'searching', 'interrupted'} or s['status'].endswith('error')],
                          'root': str(args.root)}, indent=2))
        return 0
    with run_lock(args.root):
        if prior.exists() and json.loads(prior.read_text()) != config and args.stage not in {'status', 'export'}:
            raise ValueError('Batch code/plan/settings changed. Use the original code or a new batch root.')
        if not prior.exists():
            atomic_write_json(prior, config)
        if args.stage == 'export':
            print(json.dumps(export_bundle(args.root, plan), indent=2))
            return 0
        if os.name != 'posix':
            raise ValueError('Preparation/search runs in the Linux Notebook')
        if args.install_system_deps:
            checked(['apt-get', 'update'], cwd=args.root, log=args.root / 'system-setup.log')
            checked(['apt-get', 'install', '-y', '--no-install-recommends', *SYSTEM_PACKAGES], cwd=args.root,
                    env=dict(os.environ, DEBIAN_FRONTEND='noninteractive'), log=args.root / 'system-setup.log')
        if args.stage == 'run':
            if not os.getenv('DEEPSEEK_API_KEY'):
                raise ValueError('Set DEEPSEEK_API_KEY before run. prepare does not need a key.')
            from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
            client = OpenAICompatibleJSONClient(RetracModelConfig.from_environment(provider='deepseek', model_name='deepseek-flash'))
            try:
                response = client.complete_json(system_prompt='Return a JSON object only.', user_prompt='Return {"ok": true}.')
                if response.get('ok') is not True:
                    raise ValueError('API preflight returned an unexpected response')
            except Exception:
                raise RuntimeError('Model API preflight failed; no tasks launched. Check endpoint, account and network.') from None
            # Record this small paid connectivity request separately from task usage.
            atomic_write_json(args.root / ('preflight-' + str(time.time_ns()) + '.json'), client.usage_summary())
        consecutive_search_errors = 0
        for index, task in enumerate(plan['tasks'], 1):
            identity = task['instance_id']
            state_path = args.root / 'states' / (identity + '.json')
            old = json.loads(state_path.read_text()) if state_path.exists() else {}
            if old.get('status') == 'completed' or (old.get('status', '').endswith('error') and not args.retry_errors):
                continue
            if args.stage == 'prepare' and old.get('status') == 'prepared':
                continue
            if shutil.disk_usage(args.root).free < args.min_free_gb * 1024 ** 3:
                print('Paused: insufficient free space. Increase storage and rerun the same command.', flush=True)
                break
            start = time.monotonic()
            state = {'id': identity, 'status': 'preparing'}
            atomic_write_json(state_path, state)
            print(f'[{index}/{len(plan["tasks"])}] prepare {identity}', flush=True)
            try:
                prepared = prepare_task(task, args)
                state['status'] = 'prepared'
                atomic_write_json(state_path, state)
                if args.stage == 'run':
                    state['status'] = 'searching'
                    atomic_write_json(state_path, state)
                    print(f'[{index}/{len(plan["tasks"])}] search {identity}', flush=True)
                    state = search_task(task, prepared, args, extra)
            except KeyboardInterrupt:
                state['status'] = 'interrupted'
                atomic_write_json(state_path, state)
                export_bundle(args.root, plan)
                raise
            except Exception as exc:
                state['status'] = 'search_error' if state['status'] == 'searching' else 'prepare_error'
                state['error'] = str(exc)
            state['last_attempt_seconds'] = round(time.monotonic() - start, 2)
            if old:
                state['previous_attempts'] = [*old.get('previous_attempts', []), {k: v for k, v in old.items() if k != 'previous_attempts'}]
            atomic_write_json(state_path, state)
            export_bundle(args.root, plan)
            consecutive_search_errors = consecutive_search_errors + 1 if state['status'] == 'search_error' else 0
            if state['status'] == 'model_error':
                print('Paused after model outage. Correct API/network before --retry-errors.', flush=True)
                break
            if consecutive_search_errors >= 3:
                print('Paused after three consecutive search infrastructure errors; inspect runner.log.', flush=True)
                break
        report = export_bundle(args.root, plan)
        print(f'Bundle ready: {args.root / "evaluation-bundle.zip"}', flush=True)
        states = artifacts(args.root, plan)
        success_status = {'prepared','completed'} if args.stage == 'prepare' else {'completed'}
        return 0 if all(s['status'] in success_status for s in states) else 2


if __name__ == '__main__':
    try:
        def interrupted(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Interrupted; artifacts preserved. Rerun the same command to continue.', file=sys.stderr)
        raise SystemExit(130)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'[batch error] {exc}', file=sys.stderr)
        raise SystemExit(2)
