"""Build a fixed random reserve from public metadata and known reusable env recipes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import subprocess

from benchmark_runtime import atomic_write_json, canonical_sha256
from benchmark_splits import frozen_swebench_ids
from swe_batch import environment_yaml, load_plan, MODULES


def env_key(task):
    return hashlib.sha256(environment_yaml(task['recipe']).encode()).hexdigest()[:20]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-plan', type=Path, required=True)
    parser.add_argument('--source-status', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=2026091802)
    parser.add_argument('--count', type=int, default=40)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Never overwrite a reserve plan')
    original = load_plan(args.source_plan)
    states = json.loads(args.source_status.read_text(encoding='utf-8'))
    successful = {s['id'] for s in states if s['status'] == 'prepared'}
    known_keys = {env_key(t) for t in original['tasks'] if t['instance_id'] in successful}
    excluded = set(original['excluded_ids']) | set(frozen_swebench_ids()) | {t['instance_id'] for t in original['tasks']}
    from datasets import load_dataset
    import swebench
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS, MAP_REPO_TO_INSTALL
    from swebench.harness.utils import load_cached_environment_yml
    harness = Path(swebench.__file__).resolve().parent.parent
    commit = subprocess.run(['git','-C',str(harness),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    if commit != original['harness_commit']:
        raise ValueError('Use the same pinned harness as the original public plan')
    dataset = load_dataset(original['dataset'], split=original['split'])
    fingerprint = dataset._fingerprint
    if fingerprint != original['dataset_fingerprint']:
        raise ValueError('Dataset snapshot changed; inspect before resampling')
    dataset = dataset.select_columns(['instance_id','repo','base_commit','version','problem_statement'])
    eligible = []
    for row in dataset:
        if row['instance_id'] in excluded or row['repo'] not in MODULES:
            continue
        specs = MAP_REPO_VERSION_TO_SPECS[row['repo']][row['version']]
        recipe = {k:specs[k] for k in ('python','packages','pip_packages','pre_install','install','no_use_env') if k in specs}
        recipe['repo_setup'] = MAP_REPO_TO_INSTALL.get(row['repo'], '')
        recipe['cached_environment_yml'] = load_cached_environment_yml(row['instance_id'])
        if not recipe['cached_environment_yml']:
            continue
        task = {**row, 'recipe':recipe}
        if env_key(task) in known_keys:
            eligible.append(task)
    eligible.sort(key=lambda t:t['instance_id'])
    if not 0 < args.count <= len(eligible):
        raise ValueError(f'Reserve requested {args.count}; eligible {len(eligible)}')
    tasks = random.Random(args.seed).sample(eligible, args.count)
    plan = {'schema_version':1,'dataset':original['dataset'],'split':original['split'],
            'purpose':'environment-feasible random reserve; no selection by solver outcome',
            'source_plan_sha256':original['plan_sha256'], 'sample_seed':args.seed,'count':len(tasks),
            'eligible_pool_sha256':canonical_sha256([t['instance_id'] for t in eligible]),
            'eligible_pool_ids':[t['instance_id'] for t in eligible], 'known_environment_keys':sorted(known_keys),
            'excluded_ids':sorted(excluded), 'frozen_manifest_sha256':original['frozen_manifest_sha256'],
            'dataset_fingerprint':fingerprint,'harness_commit':commit,'tasks':tasks}
    plan['plan_sha256'] = canonical_sha256(plan)
    atomic_write_json(args.output, plan)
    print(json.dumps({'count':len(tasks),'eligible':len(eligible),'repos':dict(Counter(t['repo'] for t in tasks)),
                      'plan_sha256':plan['plan_sha256']},indent=2))


if __name__ == '__main__':
    main()
