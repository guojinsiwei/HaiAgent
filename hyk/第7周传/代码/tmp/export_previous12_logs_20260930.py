"""Export only the two completed previous runs; never touch the paired-six run."""
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
from datetime import datetime, timezone

ROOTS = {
    'BestFGS-v18.1-12题': Path('/var/tmp/lizh639-lhtb-bestfgs-v181-only-r1'),
    'HAI-v0.8.2-12题': Path('/var/tmp/lizh639-lhtb-hai082-only-r1'),
}
OUTPUT = Path('/var/tmp/lizh639-previous12-export-20260930.tar.gz')
PREFIX = '上一轮12题-20260929'
SENSITIVE = re.compile(rb'(?:sk-[A-Za-z0-9_-]{24,}|Bearer\s+[A-Za-z0-9._-]{24,})')


def main():
    if OUTPUT.exists():
        raise RuntimeError('Export already exists; refusing overwrite')
    inventory = {}
    all_rows = []
    totals = []
    exported_at = datetime.now(timezone.utc).isoformat()
    with OUTPUT.open('xb') as output, tarfile.open(fileobj=output, mode='w:gz') as archive:
        def add_bytes(name, data, scan=False):
            if scan and SENSITIVE.search(data):
                raise RuntimeError('Potential credential detected; export stopped: ' + name)
            info = tarfile.TarInfo(PREFIX + '/' + name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
            inventory[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

        def add_file(root, path, label):
            if path.is_symlink() or not path.is_file():
                raise RuntimeError('Not a regular export file: ' + str(path))
            data = path.read_bytes()
            textual = path.suffix in {'.json', '.jsonl', '.log', '.txt', '.md', '.py', '.toml', '.yaml', '.yml', '.sh'}
            add_bytes(label + '/' + path.relative_to(root).as_posix(), data, scan=textual)

        for label, root in ROOTS.items():
            health = json.loads((root / 'health.json').read_text())
            rows = json.loads((root / 'summary-v2.json').read_text())
            if health['completed'] != 12 or health['active'] or health['pending'] or len(rows) != 12:
                raise RuntimeError('Expected twelve completed trials: ' + label)
            totals.append(dict(experiment=label, state=health['state'], completed=12,
                source=str(root), protocol_sha256=health.get('protocol_sha256')))
            for name in ('health.json', 'guard-health.json', 'summary.json', 'summary-v2.json',
                         'manifest.json', 'ready.json', 'images.json', 'verified-digests.json',
                         'PROTOCOL.md', 'prior-results.json', 'preparation.json',
                         'supervision.jsonl', 'supervision-v2.jsonl', 'supervisor-v2.log'):
                path = root / name
                if path.exists():
                    add_file(root, path, label)
            # Preserve exact frozen adapters plus algorithm sources for provenance.
            for path in sorted(root.glob('*.py')):
                add_file(root, path, label)
            for project in ('bestfgs-project', 'hai-project'):
                for path in sorted((root / project / 'src').rglob('*.py')):
                    if '__pycache__' not in path.parts:
                        add_file(root, path, label)
            for path in sorted((root / 'jobs').glob('*.json')):
                add_file(root, path, label)
            for path in sorted((root / 'ledger').glob('*/*')):
                if path.is_file() and path.suffix in {'.json', '.log'}:
                    add_file(root, path, label)
            for row in rows:
                report_path = Path(row['report'])
                if not report_path.is_relative_to(root / 'runs'):
                    raise RuntimeError('Report outside experiment root')
                official = json.loads(report_path.read_text())
                if official.get('verifier_result') != row.get('verifier_result'):
                    raise RuntimeError('Official/summary mismatch: ' + row['task'])
                trial = report_path.parent
                for path in sorted(trial.rglob('*')):
                    relative = path.relative_to(trial)
                    if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts:
                        continue
                    if 'host-state' in relative.parts:
                        # Filesystem snapshots dwarf actual logs; preserve command provenance only.
                        if relative.as_posix() not in {'agent/host-state/commands.jsonl', 'agent/host-state/owned.json'}:
                            continue
                    add_file(root, path, label)
                console = root / (row['method'] + '-' + row['task'] + '.console.log')
                if console.exists():
                    add_file(root, console, label)
                rewards = (official.get('verifier_result') or {}).get('rewards')
                score = (rewards or {}).get('reward')
                classification = row.get('classification') or {}
                all_rows.append(dict(experiment=label, method=row['method'], task=row['task'],
                    reward=score, all_rewards=rewards, stop_reason=classification.get('stop_reason'),
                    classification=classification, exception_info=official.get('exception_info'),
                    supervision=row.get('supervision'), mechanism_utilization=row.get('mechanism_utilization'),
                    started_at=official.get('started_at'), finished_at=official.get('finished_at'),
                    report=label + '/' + report_path.relative_to(root).as_posix()))
        record = dict(exported_at_utc=exported_at, scope='Previous completed 12-task runs only; NOT current paired-six run',
            experiments=totals, trials=all_rows)
        add_bytes('汇总数据.json', json.dumps(record, ensure_ascii=False, indent=2).encode())
        lines = ['# 上一轮已结束实验数据（各 12 题）', '',
            '本文件夹只包含 BestFGS v18.1 与 HAI v0.8.2 上一轮已结束的 24 次正式试验。',
            '**不包含当前正在跑的六题配对试验。** 数据导出时间（UTC）：' + exported_at, '',
            '两个实验均为 `completed_with_errors`：结束不等于全部通过，错误记录按原样保留。',
            '官方 reward 是任务定义的得分，不统一等同于二元成功率；空值表示缺失，不填零。',
            '原始分类存在已诊断的边界问题，未在此导出中追改；相关说明见附带的历史诊断报告。', '',
            '| 任务 | BestFGS v18.1 | HAI v0.8.2 |', '|---|---:|---:|']
        tasks = list(dict.fromkeys(row['task'] for row in all_rows))
        for task in tasks:
            values = {row['method']: row['reward'] for row in all_rows if row['task'] == task}
            lines.append('| ' + task + ' | ' + ' | '.join('缺失' if values.get(m) is None else str(values[m])
                for m in ('bestfgs', 'hai')) + ' |')
        lines += ['', '## 内容与版本关系', '',
            '- 每个实验目录包含原始汇总、官方 trial 报告、评分器输出、交付产物、模型/工具审计、调度日志和配置。',
            '- 同时保留对应的冻结算法源码和适配器，便于追溯旧成绩；未重新运行模型、评分器或实验。',
            '- 外层两个项目副本为当前 repair-v2 修复版，**不是产生这些旧成绩的版本**。不能把旧分数标成修复版成绩。',
            '- 未包含 Docker 镜像、大量 host-state 文件系统快照、密钥或完整基准仓库；命令日志和归属记录保留。',
            '- `文件校验.json` 记录导出文件的大小和 SHA-256；本说明和数据表也纳入校验。', '']
        add_bytes('实验数据说明.md', '\n'.join(lines).encode())
        manifest = json.dumps(dict(exported_at_utc=exported_at, files=inventory), ensure_ascii=False, indent=2).encode()
        add_bytes('文件校验.json', manifest)
    print(json.dumps(dict(archive=str(OUTPUT), bytes=OUTPUT.stat().st_size, files=len(inventory),
        trials=len(all_rows), sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        scores=[dict(method=r['method'], task=r['task'], reward=r['reward']) for r in all_rows]), ensure_ascii=False))


if __name__ == '__main__':
    main()
