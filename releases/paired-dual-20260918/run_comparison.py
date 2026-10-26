"""Frozen paired SWE experiment. 'plan' is read-only; 'run' makes paid API calls.

Prepared environments are reused without changing the preparation/search batch.
Never reads reference patches or benchmark grading tests.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit

from benchmark_runtime import atomic_write_json, canonical_sha256, implementation_sha256
from run_notebook import PROJECT_ROOT, run_lock, tree_digest
from swe_batch import checked, export_bundle, load_plan
from bestfgs.experiment_metrics import METRIC_VERSION, summarize_trace


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shard_assignments(identities, count):
    if not identities or len(set(identities)) != len(identities) or not 1 <= count <= len(identities):
        raise ValueError('Invalid task IDs or shard count')
    if count == 1:
        return [list(identities)]
    ordered = sorted(identities, key=lambda identity: (hashlib.sha256(identity.encode()).hexdigest(), identity))
    return [ordered[index::count] for index in range(count)]


@contextmanager
def serialized_metadata(root, timeout=60):
    # Brief cross-host NFS lock: only protocol/export metadata, never paid work.
    deadline = time.monotonic() + timeout
    while True:
        stack = ExitStack()
        try:
            stack.enter_context(run_lock(root))
        except ValueError:
            stack.close()
            if time.monotonic() >= deadline:
                raise
            time.sleep(.25)
        else:
            break
    with stack:
        yield


def common_args(args):
    return ['--provider', 'deepseek', '--model', args.model, '--base-url', args.base_url,
            '--api-key-env', 'DEEPSEEK_API_KEY', '--temperature', str(args.temperature),
            '--reasoning-effort', args.reasoning_effort, '--solve-reasoning-effort', args.reasoning_effort,
            '--max-iterations', str(args.max_iterations), '--max-tool-calls', str(args.max_tool_calls),
            '--max-commands-per-action', str(args.max_commands), '--budget-multiplier', '1',
            '--no-adaptive-budget', '--success-judge-mode', 'off', '--comparison-metrics',
            '--model-timeout', '90', '--model-max-wall-time', '600', '--model-request-attempts', '5',
            '--model-parse-attempts', '3', '--model-retry-interval', '2', '--model-max-retry-interval', '30'] + (
                ['--top-p', str(args.top_p)] if args.top_p is not None else [])


def protocol_for(args, plan):
    root = args.prepared_root.resolve()
    output = args.output_root.resolve()
    if output == root or root in output.parents or output in root.parents:
        raise ValueError('Comparison output must be separate from the prepared batch root')
    if urlsplit(args.base_url).scheme != 'https' or urlsplit(args.base_url).username or urlsplit(args.base_url).query or urlsplit(args.base_url).fragment:
        raise ValueError('Use a public HTTPS endpoint with no credentials or query tokens')
    prepared, missing, fingerprints = {}, [], {}
    for task in plan['tasks']:
        identity = task['instance_id']
        directory = root / 'prepared' / identity
        ready, freeze = directory / 'ready.json', directory / 'pip-freeze.txt'
        if not ready.is_file() or not freeze.is_file():
            missing.append(identity)
            continue
        data = json.loads(ready.read_text(encoding='utf-8'))
        if (data['id'] != identity or data['base_commit'] != task['base_commit']
                or data['recipe_sha256'] != canonical_sha256(task) or data['goal'] != task['problem_statement']):
            raise ValueError(f'Prepared task does not match frozen public plan: {identity}')
        prepared[identity] = data
        fingerprints[identity] = {'ready_sha256': file_hash(ready), 'pip_freeze_sha256': file_hash(freeze),
                                   'seed_sha256': data['seed_sha256'], 'prepared_commit': data['prepared_commit'],
                                   'task_python': data['task_python'], 'base_commit': data['base_commit']}
    protocol = {'schema_version': 1, 'metric_version': METRIC_VERSION, 'plan_sha256': plan['plan_sha256'],
                'dataset': plan['dataset'], 'split': plan['split'],
                'expected_ids': [t['instance_id'] for t in plan['tasks']],
                'implementation_sha256': implementation_sha256(PROJECT_ROOT),
                'agent_python': str(Path(sys.executable).resolve()), 'agent_python_version': sys.version,
                'common_args': common_args(args), 'task_timeout': args.task_timeout,
                'prepared': fingerprints,
                'runtime_env': {'BESTFGS_TASK_SOURCE_PATH': '1', 'OMP_NUM_THREADS': '1',
                                'OPENBLAS_NUM_THREADS': '1', 'MPLBACKEND': 'Agg'},
                'method_order': 'paired; first arm = parity of SHA256(instance_id); second arm follows immediately',
                'success_source': 'official SWE-bench Docker harness; never internal succeeded',
                'efficiency_budget': 'same main action-batch and total CLI-call caps; NOT equal LLM-token budgets'}
    count = getattr(args, 'shard_count', 1)
    if count > 1:
        protocol['sharding'] = {'count': count, 'assignment': 'SHA256(instance_id) ascending; round-robin',
                                'workers': shard_assignments(protocol['expected_ids'], count),
                                'both_methods_per_task': True}
    return protocol, prepared, missing


def check_prepared(data, frozen):
    seed, python = Path(data['workspace']), Path(data['task_python'])
    if not python.is_file() or tree_digest(seed) != frozen['seed_sha256']:
        raise ValueError('Prepared workspace/interpreter changed or is missing')
    result = subprocess.run([str(python), '-m', 'pip', 'freeze'], capture_output=True, text=True,
                            encoding='utf-8', check=True, timeout=90)
    if hashlib.sha256(result.stdout.encode('utf-8')).hexdigest() != frozen['pip_freeze_sha256']:
        raise ValueError('Installed dependencies changed since preparation; stop and prepare a new paired protocol')


def collect_state(output, identity):
    state_path = output / identity / 'status.json'
    if not state_path.is_file():
        return {'id': identity, 'status': 'search_error', 'error': 'Missing child status', 'attempt_count': 1}
    state = json.loads(state_path.read_text(encoding='utf-8'))
    attempt = Path(state['attempt'])
    result = {}
    try:
        result = json.loads((attempt / 'agent-result.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    if not isinstance(result, dict):
        result = {}
    metrics = summarize_trace(attempt / 'snapshots/cli-metrics.jsonl') if (attempt / 'snapshots/cli-metrics.jsonl').is_file() else None
    prediction = output / 'predictions.jsonl'
    return {'id': identity, 'status': 'completed' if state['status'] == 'completed' else 'search_error',
            'attempt': str(attempt), 'agent_succeeded': result.get('succeeded'), 'stop_reason': result.get('stop_reason'),
            'model_usage': result.get('model_usage', {}), 'comparison_metrics': metrics,
            'tool_calls': result.get('total_tool_calls'), 'interaction_rounds': result.get('interaction_rounds'),
            'predictions_sha256': file_hash(prediction) if prediction.is_file() else None, 'attempt_count': 1}


def run_one(args, protocol, method, identity, data):
    arm = args.output_root / method
    state_path = arm / 'states' / (identity + '.json')
    previous = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    if previous.get('status') == 'completed':
        prediction = arm / 'search' / identity / 'predictions.jsonl'
        if not prediction.is_file() or file_hash(prediction) != previous.get('predictions_sha256'):
            raise ValueError(f'Completed prediction changed/missing: {method}/{identity}')
        print(f'[skip] {method}/{identity}', flush=True)
        return True
    output = arm / 'search' / identity
    child_state = output / identity / 'status.json'
    # Recover accounting even if the parent was interrupted after launching its child.
    if previous.get('status') == 'running' and child_state.exists():
        previous = {**collect_state(output, identity), 'previous_attempts': previous.get('previous_attempts', [])}
        if previous['status'] == 'completed':
            previous['attempt_count'] = len(previous.get('previous_attempts', [])) + 1
            atomic_write_json(state_path, previous)
            return True
    if previous and not args.retry_infrastructure:
        raise ValueError(f'Preserved interrupted/failed attempt: {method}/{identity}; inspect it before --retry-infrastructure')
    check_prepared(data, protocol['prepared'][identity])
    manifest = arm / 'manifests' / (identity + '.json')
    atomic_write_json(manifest, {'schema_version': 1, 'benchmark': 'swebench', 'tasks': [data]})
    history = [*previous.get('previous_attempts', []), {k: v for k, v in previous.items() if k != 'previous_attempts'}] if previous else []
    atomic_write_json(state_path, {'id': identity, 'status': 'running', 'previous_attempts': history})
    command = [sys.executable, str(PROJECT_ROOT / 'run_notebook.py'), '--method', method,
               '--task-manifest', str(manifest), '--output-root', str(output), '--python', sys.executable,
               '--task-python', data['task_python'], '--task-timeout', str(args.task_timeout)]
    if (output / 'notebook-run.json').exists():
        command.append('--resume')
    command += ['--', *protocol['common_args']]
    started = time.monotonic()
    try:
        checked(command, cwd=PROJECT_ROOT, env=dict(os.environ, **protocol['runtime_env']),
                log=arm / ('runner.log' if getattr(args, 'shard_count', 1) == 1 else f'runner-worker-{args.shard_index}.log'),
                timeout=args.task_timeout + 300, ok_codes=(0, 2))
    finally:
        state = collect_state(output, identity)
        state.update(previous_attempts=history, attempt_count=len(history) + 1,
                     last_attempt_seconds=time.monotonic() - started)
        metrics = state.get('comparison_metrics') or {}
        if state['status'] == 'completed' and (not metrics.get('trace_complete') or metrics.get('tool_calls', 0) > args.max_tool_calls):
            state.update(status='search_error', error='Missing/incomplete metrics or actual tool calls exceeded the common cap')
        atomic_write_json(state_path, state)
    try:
        check_prepared(data, protocol['prepared'][identity])
    except (OSError, ValueError, subprocess.SubprocessError):
        state.update(status='search_error', error='Shared task environment changed during execution; paired run is invalid')
        atomic_write_json(state_path, state)
        raise
    return state['status'] == 'completed'


def export_arms(args, plan, protocol):
    for method in ('bestfgs', 'raw'):
        arm = args.output_root / method
        arm.mkdir(parents=True, exist_ok=True)
        atomic_write_json(arm / 'batch.json', {'plan_sha256': plan['plan_sha256'], 'protocol': protocol})
        export_bundle(arm, plan, model_name=method + '-deepseek',
                      comparison={'method': method, 'protocol_sha256': canonical_sha256(protocol), 'protocol': protocol})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('plan', 'run', 'export'))
    parser.add_argument('--plan', type=Path, default=PROJECT_ROOT / 'examples/swe100-plan.json')
    parser.add_argument('--prepared-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--method', choices=('both', 'bestfgs', 'raw'), default='both')
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--base-url', default='https://api.deepseek.com')
    parser.add_argument('--temperature', type=float, default=.2)
    parser.add_argument('--top-p', type=float)
    parser.add_argument('--reasoning-effort', choices=('low', 'high', 'max'), default='high')
    parser.add_argument('--max-iterations', type=int, default=24)
    parser.add_argument('--max-tool-calls', type=int, default=80)
    parser.add_argument('--max-commands', type=int, default=4)
    parser.add_argument('--task-timeout', type=int, default=14400)
    parser.add_argument('--retry-infrastructure', action='store_true')
    parser.add_argument('--shard-count', type=int, default=1)
    parser.add_argument('--shard-index', type=int, default=0)
    args = parser.parse_args(argv)
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error('Require 0 <= shard-index < shard-count')
    if args.shard_count > 1 and args.method != 'both':
        parser.error('Sharded comparison requires both methods per task')
    if min(args.max_iterations, args.max_tool_calls, args.max_commands, args.task_timeout) < 1:
        parser.error('Budgets/timeouts must be positive')
    if not math.isfinite(args.temperature) or not 0 <= args.temperature <= 2 or (args.top_p is not None and not 0 < args.top_p <= 1):
        parser.error('temperature must be finite in [0,2]; top-p, if set, in (0,1]')
    args.prepared_root, args.output_root = args.prepared_root.resolve(), args.output_root.resolve()
    plan = load_plan(args.plan)
    assigned = shard_assignments([t['instance_id'] for t in plan['tasks']], args.shard_count)[args.shard_index]
    protocol, prepared, missing = protocol_for(args, plan)
    if args.action == 'plan':
        print(json.dumps({'protocol_sha256': canonical_sha256(protocol), 'metric_version': METRIC_VERSION,
                          'plan_sha256': plan['plan_sha256'], 'common_args': protocol['common_args'],
                          'total': len(plan['tasks']), 'ready': len(prepared), 'missing': missing,
                          'shard_index': args.shard_index, 'assigned_ids': assigned,
                          'output_root': str(args.output_root), 'paid_calls_started': False}, ensure_ascii=False, indent=2))
        return 0 if not missing else 2
    if missing:
        raise ValueError(f'{len(missing)} tasks not prepared; fixed denominator is retained. Run plan for their IDs.')
    # Each shard owns disjoint task directories. Common metadata is serialized.
    worker_root = args.output_root / 'worker-locks' / str(args.shard_index)
    with run_lock(worker_root):
        if args.action == 'run' and not os.environ.get('DEEPSEEK_API_KEY'):
            raise ValueError('Set DEEPSEEK_API_KEY in this terminal; do not put it in a command/file')
        with serialized_metadata(args.output_root):
            lock = args.output_root / 'comparison-protocol.json'
            if lock.exists():
                if json.loads(lock.read_text(encoding='utf-8')) != protocol:
                    raise ValueError('Code/config/preparation changed; preserve results and use a new comparison output root')
            elif args.action == 'export':
                raise ValueError('No comparison run exists')
            else:
                atomic_write_json(lock, protocol)
            if args.action == 'export':
                export_arms(args, plan, protocol)
                return 0
        worker_status = args.output_root / 'workers' / f'{args.shard_index}.json'
        worker = {'shard_index': args.shard_index, 'assigned_ids': assigned, 'hostname': __import__('socket').gethostname(),
                  'pid': os.getpid(), 'protocol_sha256': canonical_sha256(protocol), 'status': 'running'}
        atomic_write_json(worker_status, worker)
        try:
            for identity in assigned:
                methods = ['bestfgs', 'raw'] if int(hashlib.sha256(identity.encode()).hexdigest(), 16) % 2 == 0 else ['raw', 'bestfgs']
                for method in methods:
                    if args.method != 'both' and args.method != method:
                        continue
                    print(f'[comparison] {method}/{identity}', flush=True)
                    if not run_one(args, protocol, method, identity, prepared[identity]):
                        worker['status'] = 'infrastructure_error'
                        print('Infrastructure/runtime failure: batch stopped; no automatic solution retries.', file=sys.stderr)
                        return 2
            worker['status'] = 'completed'
        finally:
            if worker['status'] == 'running':
                worker['status'] = 'interrupted_or_error'
            atomic_write_json(worker_status, worker)
            with serialized_metadata(args.output_root):
                export_arms(args, plan, protocol)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'[comparison error] {exc}', file=sys.stderr)
        raise SystemExit(2)
