"""Freeze a hardware-compatible development sample using PUBLIC metadata only."""
import hashlib
import json
from pathlib import Path
import random
import tomllib

ROOT = Path('/home/ecs-user/terminalbench-paired36-20260923')
PROJECT = Path('/home/ecs-user/BestFGS-blocking-memory-v12')
DATASET = ROOT / 'datasets/terminal-bench-2'


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def write_once(path, data):
    text = json.dumps(data, indent=2, ensure_ascii=True) + '\n'
    if path.exists():
        if path.read_text() != text:
            raise RuntimeError(f'Frozen file mismatch: {path.name}')
        return
    with path.open('x') as stream:
        stream.write(text)


def main():
    tasks = sorted(DATASET.glob('*/task.toml'))
    if len(tasks) != 89:
        raise RuntimeError('Incomplete or changed 89-task dataset; no sampling')
    frozen_path = PROJECT / 'benchmark_splits/frozen_test_set_v1.json'
    protected = set(json.loads(frozen_path.read_text())['terminal_bench_2']['task_names'])
    audit, eligible, details = [], [], {}
    for path in tasks:
        config = tomllib.loads(path.read_text())
        name = 'terminal-bench/' + path.parent.name
        env = config['environment']
        reason = None
        if name in protected:
            reason = 'frozen_test'
        elif env.get('gpus', 0) or env.get('cpus', 1) > 4 or env.get('memory_mb', 0) > 12288 or env.get('storage_mb', 0) > 81920:
            reason = 'exceeds_4cpu_12GiB_80GiB_task_envelope'
        elif not env.get('docker_image'):
            reason = 'no_prebuilt_official_image'
        details[name] = {'id': name, 'task_dir': str(path.parent), 'environment': env,
                         'agent_timeout': config.get('agent', {}).get('timeout_sec', 900),
                         'verifier_timeout': config.get('verifier', {}).get('timeout_sec', 900),
                         'public_config_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        audit.append({'id': name, 'exclusion': reason})
        if reason is None:
            eligible.append(name)
    if len(eligible) < 36:
        raise RuntimeError('Insufficient eligible tasks; do not silently weaken hardware limits')
    order = list(eligible)
    random.Random(20260923).shuffle(order)
    selected = order[:36]
    data = {'dataset': 'terminal-bench/terminal-bench-2', 'seed': 20260923,
            'sampling': 'uniform shuffle of hardware-compatible non-frozen development pool; first 36',
            'dataset_count': 89, 'eligible_count': len(eligible), 'tasks': [details[n] for n in selected],
            'reserves_not_for_runtime_replacement': order[36:], 'audit': audit,
            'frozen_manifest_sha256': hashlib.sha256(frozen_path.read_bytes()).hexdigest()}
    data['selection_sha256'] = digest(data)
    (ROOT / 'control').mkdir(exist_ok=True)
    write_once(ROOT / 'control/task-selection.json', data)
    print(json.dumps({'selected': len(selected), 'eligible': len(eligible), 'excluded': [x for x in audit if x['exclusion']], 'sha256': data['selection_sha256']}))


if __name__ == '__main__':
    main()
