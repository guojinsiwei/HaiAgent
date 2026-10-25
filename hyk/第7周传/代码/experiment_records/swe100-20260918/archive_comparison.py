"""Freeze the downloaded public selection and preparation evidence for comparisons."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent / 'preparation-v1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def main():
    plan_bytes = (ROOT / 'swe100-plan.json').read_bytes()
    plan = json.loads(plan_bytes)
    assert canonical({k:v for k,v in plan.items() if k != 'plan_sha256'}) == plan['plan_sha256']
    ids = [t['instance_id'] for t in plan['tasks']]
    assert len(ids) == len(set(ids)) == 100
    assert not set(ids) & set(plan['excluded_ids'])
    with zipfile.ZipFile(ROOT / 'preparation-evidence.zip') as archive:
        bundle = json.loads(archive.read('bundle.json'))
        for name, digest in bundle['sha256'].items():
            assert sha(archive.read(name)) == digest, name
        states = json.loads(archive.read('summary.json'))
        batch = json.loads(archive.read('batch.json'))
    assert bundle['expected_ids'] == ids == [s['id'] for s in states]
    assert bundle['plan_sha256'] == batch['plan_sha256'] == plan['plan_sha256']
    assert all(s['status'] in {'prepared', 'prepare_error'} for s in states)
    counts = dict(Counter(s['status'] for s in states))
    lock = {
        'schema_version': 1,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'development_comparison_selection_not_frozen_test',
        'dataset': plan['dataset'], 'split': plan['split'],
        'dataset_fingerprint': plan['dataset_fingerprint'],
        'sample_seed': plan['sample_seed'],
        'plan_sha256': plan['plan_sha256'],
        'ordered_instance_ids': ids,
        'task_revisions': [{'instance_id': t['instance_id'], 'repo':t['repo'],
                            'base_commit':t['base_commit'], 'version':t['version']} for t in plan['tasks']],
        'initial_preparation_counts': counts,
        'failed_preparation_ids': [s['id'] for s in states if s['status'] == 'prepare_error'],
        'initial_batch_configuration': batch,
        'rules': [
            'Reuse exactly the same selected IDs, order, and base commits for every method; never resample failed tasks.',
            'The 73 currently prepared tasks are not a replacement benchmark. Retain all 100 tasks and the 27 infrastructure failures.',
            'Repair and validate environments before freezing the final shared environment specification for comparisons.',
            'Use clean independent workspaces, outputs and memory per method; do not share solution patches or learned memory between methods.',
            'Record model, sampling parameters, budget protocol, retries, task environment versions and evaluation harness version.',
            'Report infrastructure failures separately; use a common evaluation protocol and declare any common-subset analysis explicitly.',
        ],
        'source_files': {'swe100-plan.json':sha(plan_bytes),
                         'preparation-evidence.zip':sha((ROOT / 'preparation-evidence.zip').read_bytes())},
    }
    outputs = {
        'comparison-lock.json': json.dumps(lock, ensure_ascii=False, indent=2) + '\n',
        'task-ids-100.txt': '\n'.join(ids) + '\n',
        'prepare-errors-27.txt': '\n'.join(lock['failed_preparation_ids']) + '\n',
        'preparation-status.json': json.dumps(states, ensure_ascii=False, indent=2) + '\n',
        'README.md': '# SWE100 对比实验选题留档\n\n'
            '本目录保存第一次环境准备结束时的证据，不是正式搜索或官方评测结果。\n\n'
            f'- 选题：100 题，种子 {plan["sample_seed"]}，顺序固定。\n'
            f'- 环境准备：{counts.get("prepared", 0)} 成功，{counts.get("prepare_error", 0)} 失败。\n'
            f'- 原始清单摘要：`{plan["plan_sha256"]}`。\n'
            '- `task-ids-100.txt` 是对比实验复用的完整题目清单。\n'
            '- `prepare-errors-27.txt` 是待修复环境的题目，不应换题或直接剔除。\n'
            '- `swe100-plan.json` 保留每题基准提交、公开问题和原始环境配方。\n'
            '- `comparison-lock.json` 保留选题身份、初始预算和对比实验约束。\n'
            '- `preparation-evidence.zip` 保留初始状态、准备环境说明和 pip freeze。\n\n'
            '这是项目非冻结开发池中的实验；没有使用项目预留的冻结测试题。数据集自身 split 名为 test。\n'
            '环境修复后另存版本，不能覆盖这份初始证据。不同方法使用独立工作区、输出和记忆；模型参数及预算按预先声明的协议控制。\n',
    }
    for name, text in outputs.items():
        with (ROOT / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    target = ROOT.parent / 'swe100-comparison-lock-v1.zip'
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in ['swe100-plan.json', 'preparation-evidence.zip', *outputs]:
            archive.write(ROOT / name, name)
    print(json.dumps({'counts': counts, 'plan_sha256':plan['plan_sha256'],
                      'archive':str(target), 'archive_sha256':sha(target.read_bytes())}, indent=2))


if __name__ == '__main__':
    main()
