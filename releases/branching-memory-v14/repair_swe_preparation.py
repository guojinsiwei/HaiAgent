"""Repair only failed preparation tasks, keeping the fixed plan and original batch lock.

No search/API/official grading is performed. Every environment gets a fresh prefix.
Run from a new project release; never patch the old immutable batch implementation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import signal
import time
import uuid

from benchmark_runtime import atomic_write_json, implementation_sha256
from run_notebook import run_lock
from swe_batch import ROOT, export_bundle, load_plan, prepare_task, repair_build_pins


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--plan', type=Path, default=ROOT / 'examples/swe100-plan.json')
    parser.add_argument('--expected-failures', type=int, default=15)
    parser.add_argument('--conda', default='/root/miniconda3/bin/conda')
    parser.add_argument('--prepare-timeout', type=int, default=3600)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    args.repair_build = True
    if args.root == Path(args.root.anchor) or args.root == ROOT or args.root in ROOT.parents or ROOT in args.root.parents:
        raise ValueError('Use the dedicated existing batch root, outside the project')
    if args.prepare_timeout <= 0 or args.expected_failures < 1:
        raise ValueError('Invalid timeout/count')
    plan = load_plan(args.plan)
    batch_path = args.root / 'batch.json'
    if json.loads(batch_path.read_text())['plan_sha256'] != plan['plan_sha256']:
        raise ValueError('Fixed plan mismatch')
    with run_lock(args.root):
        targets, saved, protected = [], {}, {}
        for task in plan['tasks']:
            identity = task['instance_id']
            path = args.root / 'states' / (identity + '.json')
            state = json.loads(path.read_text())
            if state['status'] in {'preparing', 'searching'}:
                raise ValueError('Active task state exists; inspect/recover it before repair')
            if state['status'] == 'prepare_error':
                if (args.root / 'prepared' / identity / 'ready.json').exists():
                    raise ValueError('Failed task unexpectedly has a ready manifest; inspect before overwriting')
                repair_build_pins(task)  # reject unknown versions before any mutation
                targets.append(task)
                saved[identity] = state
            else:
                protected[str(path)] = file_sha(path)
                for name in ('ready.json', 'pip-freeze.txt'):
                    artifact = args.root / 'prepared' / identity / name
                    if artifact.exists():
                        protected[str(artifact)] = file_sha(artifact)
        if len(targets) != args.expected_failures:
            raise ValueError(f'Expected {args.expected_failures} failed tasks, found {len(targets)}; no installations started')
        record = {'schema_version': 1, 'adapter': 'notebook-prepfix-v2', 'plan_sha256': plan['plan_sha256'],
                  'original_batch_sha256': file_sha(batch_path), 'implementation_sha256': implementation_sha256(ROOT),
                  'targets': [t['instance_id'] for t in targets], 'before': saved, 'protected_sha256': protected,
                  'build_pins': {t['instance_id']: repair_build_pins(t) for t in targets}, 'results': []}
        if args.dry_run:
            print(json.dumps({k:v for k,v in record.items() if k not in {'protected_sha256','before'}}, indent=2))
            return 0
        if os.name != 'posix':
            raise ValueError('Actual preparation runs in the Linux Notebook')
        journal = args.root / 'repairs' / ('prepfix-v2-' + uuid.uuid4().hex[:12]) / 'repair.json'
        atomic_write_json(journal, record)
        print(f'[repair audit] {journal}', flush=True)
        try:
            for index, task in enumerate(targets, 1):
                identity = task['instance_id']
                before = saved[identity]
                state_path = args.root / 'states' / (identity + '.json')
                history = [*before.get('previous_attempts', []), {k:v for k,v in before.items() if k != 'previous_attempts'}]
                state = {'id': identity, 'status': 'preparing', 'previous_attempts': history, 'repair_journal': str(journal)}
                atomic_write_json(state_path, state)
                started = time.monotonic()
                print(f'[repair {index}/{len(targets)}] {identity}', flush=True)
                try:
                    ready = prepare_task(task, args)
                    state.update(status='prepared', preparation_adapter=ready['preparation_adapter'])
                except KeyboardInterrupt:
                    state.update(status='prepare_error', error='Preparation repair interrupted; artifacts retained')
                    raise
                except Exception as exc:
                    state.update(status='prepare_error', error=str(exc))
                finally:
                    state['last_attempt_seconds'] = round(time.monotonic() - started, 2)
                    atomic_write_json(state_path, state)
                    record['results'].append(state)
                    atomic_write_json(journal, record)
                    export_bundle(args.root, plan)
                    print(f'[repair result] {identity}: {state["status"]}', flush=True)
        finally:
            if file_sha(batch_path) != record['original_batch_sha256']:
                raise RuntimeError('Original batch configuration changed unexpectedly')
            for path, expected in protected.items():
                if file_sha(path) != expected:
                    raise RuntimeError(f'Previously prepared artifact changed: {path}')
            record['protected_artifacts_unchanged'] = True
            record['finished_counts'] = dict(Counter(s['status'] for s in record['results']))
            atomic_write_json(journal, record)
            export_bundle(args.root, plan)
        print(json.dumps(record['finished_counts']), flush=True)
        return 0 if all(s['status'] == 'prepared' for s in record['results']) else 2


if __name__ == '__main__':
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
