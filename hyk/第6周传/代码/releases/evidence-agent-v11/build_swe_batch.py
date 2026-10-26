"""Export a reproducible PUBLIC task plan on the evaluation host, never gold/tests."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
from collections import Counter
from pathlib import Path

from benchmark_runtime import atomic_write_json, canonical_sha256
from benchmark_splits import FROZEN_CHECKSUM, frozen_swebench_ids


def select_ids(ids, count, seed, excluded):
    pool = sorted(set(ids) - set(excluded))
    if not 0 < count <= len(pool):
        raise ValueError(f"Requested {count} tasks from eligible pool of {len(pool)}")
    return random.Random(seed).sample(pool, count), pool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--seed', type=int, default=20260918)
    parser.add_argument('--exclude-history', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Plan already exists; reuse it or choose a NEW output. Never resample on resume.')
    from datasets import load_dataset
    import swebench
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS, MAP_REPO_TO_INSTALL
    from swebench.harness.test_spec.python import get_requirements, get_environment_yml
    from swebench.harness.utils import load_cached_environment_yml
    dataset = load_dataset('SWE-bench/SWE-bench_Verified', split='test')
    excluded = set(frozen_swebench_ids()) | {'sympy__sympy-16450'}
    if args.exclude_history:
        for path in args.exclude_history.glob('predictions-*.jsonl'):
            for line in path.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    excluded.add(json.loads(line)['instance_id'])
    identities, pool = select_ids(dataset['instance_id'], args.count, args.seed, excluded)
    by_id = {row['instance_id']: row for row in dataset}
    tasks = []
    for identity in identities:
        # Explicit allowlist: do not serialize row, patch, test_patch or test labels.
        row = by_id[identity]
        public = {key: row[key] for key in ('instance_id', 'repo', 'base_commit', 'version', 'problem_statement')}
        specs = MAP_REPO_VERSION_TO_SPECS[row['repo']][row['version']]
        recipe = {key: specs[key] for key in ('python', 'packages', 'pip_packages', 'pre_install', 'install', 'no_use_env') if key in specs}
        recipe['repo_setup'] = MAP_REPO_TO_INSTALL.get(row['repo'], '')
        cached = load_cached_environment_yml(identity)
        recipe['cached_environment_yml'] = cached
        if not cached and specs.get('packages') == 'requirements.txt':
            recipe['requirements_text'] = get_requirements(row)
        if not cached and specs.get('packages') == 'environment.yml':
            recipe['environment_yml'] = get_environment_yml(row, 'bestfgs-task')
        public['recipe'] = recipe
        tasks.append(public)
    root = Path(swebench.__file__).resolve().parent.parent
    commit = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    plan = {'schema_version': 1, 'dataset': 'SWE-bench/SWE-bench_Verified', 'split': 'test',
            'purpose': 'development_batch_not_frozen_test', 'sample_seed': args.seed,
            'count': len(tasks), 'eligible_pool_sha256': canonical_sha256(pool),
            'excluded_ids': sorted(excluded), 'frozen_manifest_sha256': FROZEN_CHECKSUM.read_text().strip(),
            'dataset_fingerprint': dataset._fingerprint, 'harness_commit': commit,
            'tasks': tasks}
    plan['plan_sha256'] = canonical_sha256(plan)
    atomic_write_json(args.output, plan)
    print(json.dumps({'path': str(args.output), 'count': len(tasks), 'repos': dict(Counter(t['repo'] for t in tasks)),
                      'cached_envs': sum(bool(t['recipe']['cached_environment_yml']) for t in tasks),
                      'plan_sha256': plan['plan_sha256']}, indent=2))


if __name__ == '__main__':
    main()
