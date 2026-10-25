"""Read-only multi-campaign result audit; no logs/prompts/secrets or model calls."""
import hashlib
import json
from pathlib import Path
import statistics
import time

SPECS = [
    ('small', 'DH 原版 v9', '/var/tmp/lizh639-longcli-dh-raw-full20-20261004', 'dh', 20),
    ('small', 'RAW（参考）', '/var/tmp/lizh639-longcli-dh-raw-full20-20261004', 'raw', 20),
    ('small', 'DH 子目标+1234 无工具', '/mnt/sdb/home/lizh639/longcli-dh-controls-paired40-20261008', 'dh_1234_no_tools', 20),
    ('small', 'DH 子目标+1234 带工具', '/mnt/sdb/home/lizh639/longcli-dh-controls-paired40-20261008', 'dh_1234_tools', 20),
    ('small', 'DSH 字节上下文修复版', '/var/tmp/lizh639-longcli-dsh20-byte-context-repair-20261006', 'dsh', 20),
    ('small', 'Recuris Frozen', '/mnt/sdb/home/lizh639/longcli-resume-five-20261007/recuris_frozen-resume-20261007', 'recuris_frozen', 20),
    ('small', 'Re-TRAC', '/mnt/sdb/home/lizh639/longcli-resume-five-20261007/retrac-resume-20261007', 'retrac', 20),
    ('small', 'LATS', '/var/tmp/lizh639-lats-recovery4-two-20261008', 'lats', 20),
    ('small', 'TACO', '/var/tmp/lizh639-longcli-lats-taco-recovery2-20261007/taco', 'taco', 20),
    ('small', 'Reflexion', '/var/tmp/lizh639-longcli-reflexion-recovery-20261006', 'reflexion', 20),
    ('large', 'DH 原版 v9 大预算', '/mnt/sdb/home/lizh639/longcli-resume-five-20261007/dh-resume-20261007', 'dh', 20),
    ('large', 'DSH 大预算', '/var/tmp/lizh639-longcli-dsh20-repair2-20261005', 'dsh', 20),
    ('large', 'DH 子目标+1342', '/var/tmp/longcli-dh-routing3x7-20261008', '1342', 7),
    ('large', 'Recuris Frozen', '/mnt/sdb/home/lizh639/longcli-recuris-taco-large7-20261009/recuris_frozen', 'recuris_frozen', 7),
    ('large', 'TACO', '/mnt/sdb/home/lizh639/longcli-recuris-taco-large7-20261009/taco', 'taco', 7),
]


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chosen_reports(root, method):
    reports = {}
    plan = read(root / 'resume-plan.json')
    for item in plan.get('preserved', []):
        file = Path(item['report'])
        assert file.is_file() and digest(file) == item['report_sha256'], str(file)
        reports[item['task']] = file
    protocol = read(root / 'protocol.json')
    for item in protocol.get('recovery', {}).get('reused_deliveries', []):
        source = Path(item['source']); task = item['task']
        file = source.parents[1] / 'grades' / source.name / 'result.json'
        if task not in reports and file.is_file(): reports[task] = file
    for file in (root / 'grades').glob(method + '--*/result.json'):
        task = file.parent.name.split('--', 1)[1]
        assert task not in reports, 'Duplicate selected task: ' + task
        reports[task] = file
    # Authorized grading-only correction: same immutable DH pgtbl artifact.
    if root.name == 'lizh639-longcli-dh-raw-full20-20261004' and method == 'dh':
        for file in (root / 'grades').glob('roundtrip--outer-clock-fix--61810_pgtbl/result.json'):
            reports['61810_pgtbl'] = file
    return reports


def summary_for(report, task, method, target_root):
    root = report.parents[2]
    job = method + '--' + task
    candidates = [root / 'jobs' / job / 'summary.json', root / 'incoming' / job / 'summary.json',
                  root / 'runs' / job / 'summary.json']
    # Native DH/raw histories have worker-prefixed or rotating job directories.
    for folder in ('jobs', 'incoming', 'runs'):
        candidates.extend((root / folder).glob('*' + method + '--' + task + '/summary.json'))
    if report.parent.name.startswith('roundtrip--'):
        candidates.extend((target_root / 'runs').glob('*' + method + '--' + task + '/summary.json'))
    for file in candidates:
        if file.is_file():
            item = read(file)
            if item.get('fixture') or item.get('mock'): continue
            return file, item
    return None, {}


def counters(summary):
    api = summary.get('actual_api_attempts', summary.get('api_attempts'))
    usage = summary.get('model_usage', {})
    if api is None and usage:
        if 'api_requests' in usage: api = usage['api_requests']
        elif isinstance(usage, dict) and all(isinstance(x, dict) for x in usage.values()):
            vals = [x.get('api_requests') for x in usage.values()]
            if vals and all(type(x) is int for x in vals): api = sum(vals)
    tools = summary.get('tool_calls', summary.get('root_tool_dispatches'))
    return api, tools


def collect():
    groups = []
    for budget, name, root_name, method, expected in SPECS:
        root = Path(root_name); protocol = read(root / 'protocol.json')
        reports = chosen_reports(root, method); rows = []
        for task, file in sorted(reports.items()):
            grade = read(file); score = grade.get('f2p', {}).get('step_score')
            summary_path, summary = summary_for(file, task, method, root)
            api, tools = counters(summary)
            rows.append({'task': task, 'report': str(file), 'report_sha256': digest(file),
                'scored': grade.get('grading_state') == 'complete' and isinstance(score, (float, int)),
                'score': score, 'official_success': grade.get('official_success'),
                'grade_cleanup': grade.get('grading_container_destroyed', grade.get('container_destroyed')),
                'summary': str(summary_path) if summary_path else None,
                'summary_sha256': digest(summary_path) if summary_path else None,
                'api_attempts': api, 'tools': tools, 'stop_reason': summary.get('stop_reason'),
                'model_fault': summary.get('model_fault'), 'engineering_fault': summary.get('engineering_fault'),
                'artifact_matches': grade.get('artifact_sha256') == summary.get('artifact', {}).get('sha256')
                    if summary.get('artifact') else None})
        valid = [r for r in rows if r['scored']]
        values = [r['score'] for r in valid]
        apis = [r['api_attempts'] for r in valid if type(r['api_attempts']) is int]
        tools = [r['tools'] for r in valid if type(r['tools']) is int]
        groups.append({'budget': budget, 'name': name, 'root': root_name, 'method': method,
            'expected': expected, 'scored': len(valid), 'missing': expected - len(valid),
            'official_successes': sum(r['official_success'] is True for r in valid),
            'success_flag_missing': sum(r['official_success'] is None for r in valid),
            'mean_score': statistics.mean(values) if values else None,
            'mean_api_attempts': statistics.mean(apis) if len(apis) == len(valid) and valid else None,
            'mean_tools': statistics.mean(tools) if len(tools) == len(valid) and valid else None,
            'api_coverage': len(apis), 'tool_coverage': len(tools),
            'capacity': {k: protocol.get(k) for k in ('max_tokens', 'output_tokens_per_call', 'context_tokens',
                'context_selection', 'context_limit', 'input_bytes', 'actual_api_attempts_per_task', 'max_tools')},
            'rows': rows})
    return {'generated_at_unix': time.time(), 'data_status': 'ACTUAL_RUN',
            'metric_definitions': {'success': 'official_success == true (F2P and P2P)',
                'score': 'mean official F2P step_score, scored tasks only; negatives retained',
                'api_interactions': 'actual provider attempts, all roles and retries, scored tasks only',
                'environment_interactions': 'all executed tool calls/root tool dispatches, scored tasks only',
                'redundancy': 'needs contextual audit; not substituted with text repetition or rejected proposals'},
            'groups': groups}


if __name__ == '__main__': print(json.dumps(collect(), ensure_ascii=False))
