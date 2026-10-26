"""SSH polling and reconciliation, no model calls or remote writes."""
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parent
DISPLAY = {'lats': 'LATS', 'taco': 'TACO', 'retrac': 'Re-TRAC',
           'dh': 'DH 大预算', 'dh_tools': 'DH 小预算（三工具）',
           'dh_1234_tools': 'DH 1234（三工具）',
           'dh_1234_no_tools': 'DH 1234（无三工具）', 'recuris_frozen': 'Recuris'}
STATE = {'running': '运行中', 'stalled': '心跳超时', 'graded': '已评分',
         'awaiting_grade': '等待评分', 'failed': '工程失败', 'interrupted': '已中断',
         'stopped': '进程已停止', 'pending': '未开始'}


def load_config():
    return json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))


def fetch_node(node, key):
    began = time.time()
    payload = base64.b64encode(json.dumps(node, ensure_ascii=False).encode()).decode()
    command = shlex.quote(node['python']) + ' - ' + shlex.quote(payload)
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    try:
        result = subprocess.run(['ssh', '-i', key, '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=8', '-o', 'ServerAliveCountMax=2',
            node['host'], command], input=(ROOT / 'remote_probe.py').read_text(encoding='utf-8'),
            text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=45, **options)
        if result.returncode:
            stderr = result.stderr.lower()
            reason = ('SSH 认证失败' if 'permission denied' in stderr else
                      'SSH 主机密钥待确认' if 'host key verification' in stderr else
                      '连接超时' if 'timed out' in stderr else
                      '主机地址无法解析' if 'could not resolve' in stderr else 'SSH 连接/采集失败')
            return {'id': node['id'], 'ok': False, 'error': reason, 'attempted_at': time.time()}
        if len(result.stdout) > 12_000_000:
            raise ValueError('response_limit')
        data = json.loads(result.stdout)
        if data.get('node') != node['id'] or not isinstance(data.get('campaigns'), list):
            raise ValueError('response_schema')
        return {'id': node['id'], 'ok': True, 'data': data, 'latency': time.time() - began,
                'attempted_at': time.time()}
    except subprocess.TimeoutExpired:
        return {'id': node['id'], 'ok': False, 'error': '45 秒采集超时', 'attempted_at': time.time()}
    except (OSError, ValueError):
        return {'id': node['id'], 'ok': False, 'error': '采集结果不可用', 'attempted_at': time.time()}


def poll(config):
    with ThreadPoolExecutor(max_workers=len(config['nodes'])) as pool:
        futures = [pool.submit(fetch_node, node, config['ssh_key']) for node in config['nodes']]
        for future in as_completed(futures):
            yield future.result()


def summarize(campaign):
    tasks = campaign.get('tasks', [])
    counts = {s: sum(t['state'] == s for t in tasks) for s in STATE}
    active = counts['running'] + counts['stalled']
    failed = counts['failed'] + counts['stopped'] + counts['interrupted']
    expected = campaign.get('expected', len(tasks))
    graded = counts['graded']
    if graded >= expected and expected:
        status = '已全部完成'
    elif active:
        status = '运行中' if not counts['stalled'] else '运行中 · 心跳超时'
    elif counts['awaiting_grade'] and campaign.get('grader_alive'):
        status = '正在评分'
    elif campaign.get('controller_alive'):
        status = '调度中'
    elif campaign.get('raw_state') == 'external_workers_running':
        status = '等待外部工作节点'
    elif campaign.get('raw_state') == 'awaiting_credentials':
        status = '等待本地输入 API 密钥'
    elif failed:
        status = '已停止 · 需补跑'
    elif counts['awaiting_grade']:
        status = '已提交 · 评分未运行'
    else:
        status = '未启动/已停止'
    values = [t['score'] for t in tasks if t['state'] == 'graded' and isinstance(t.get('score'), (int, float))]
    return {**campaign, 'counts': counts, 'active_count': active, 'failed_count': failed,
            'graded_count': graded, 'status': status,
            'mean': sum(values) / len(values) if values else None,
            'successes': sum(t.get('official_success') is True for t in tasks if t['state'] == 'graded')}


def reconcile(node_states, history=False):
    campaigns = []
    for node, state in node_states.items():
        for c in state.get('data', {}).get('campaigns', []):
            campaigns.append({**c, 'connection_ok': state.get('ok', False)})
    if history:
        return sorted([summarize(c) for c in campaigns], key=lambda c: (bool(c['active_count']), c['created']), reverse=True)
    grouped = {}
    for c in campaigns:
        grouped.setdefault(c['method'], []).append(c)
    result = []
    for method, versions in grouped.items():
        newest = max(versions, key=lambda c: c['created'])
        # Cube worker partitions and college official grading share a source cohort.
        cohort = [c for c in versions if c['cohort'] == newest['cohort']]
        primary = max(cohort, key=lambda c: (c['node'] == 'college', c['created']))
        merged = {t['task']: dict(t) for t in primary['tasks']}
        for other in cohort:
            if other['id'] == primary['id']:
                continue
            for t in other['tasks']:
                previous = merged.get(t['task'])
                if previous and previous['state'] == 'graded':
                    continue
                if previous is None or (t.get('updated') or 0) > (previous.get('updated') or 0):
                    merged[t['task']] = dict(t)
        # Some older one-task repair scripts have no preserved manifest. Carry
        # forward only VERIFIED graded tasks absent from the newest task set.
        # A new attempt for a task already in `merged` always remains authoritative.
        if method in DISPLAY:
            for older in sorted(versions, key=lambda c: c['created'], reverse=True):
                if older.get('model') != primary.get('model') or older.get('output_tokens') != primary.get('output_tokens'):
                    continue
                for t in older['tasks']:
                    if t['task'] not in merged and t['state'] == 'graded':
                        merged[t['task']] = dict(t)
        for t in merged.values():
            t['connection_ok'] = node_states.get(t['node'], {}).get('ok', False)
        merged_campaign = {**primary, 'tasks': list(merged.values()),
            'sources': [{'node': c['node'], 'root': c['root'], 'connection_ok': c['connection_ok']} for c in cohort],
            'expected': max(c['expected'] for c in cohort),
            'controller_alive': any(c['controller_alive'] and c['connection_ok'] for c in cohort),
            'grader_alive': any(c['grader_alive'] and c['connection_ok'] for c in cohort)}
        item = summarize(merged_campaign)
        if not primary['connection_ok']:
            item['status'] = '节点离线 · 上次：' + item['status']
        if method in DISPLAY or item['active_count']:
            result.append(item)
    order = list(DISPLAY)
    return sorted(result, key=lambda c: (order.index(c['method']) if c['method'] in order else 99, c['method']))


def update_state(states, result):
    previous = states.get(result['id'], {})
    states[result['id']] = {**previous, **result}


def save_cache(states):
    path = ROOT / 'cache.json'
    temp = ROOT / 'cache.json.tmp'
    temp.write_text(json.dumps(states, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def load_cache():
    try:
        states = json.loads((ROOT / 'cache.json').read_text(encoding='utf-8'))
        for state in states.values():
            state['ok'] = False
            state['error'] = '正在重新连接；显示上次快照'
        return states
    except (OSError, ValueError, AttributeError):
        return {}


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    config = load_config()
    states = {}
    for result in poll(config):
        update_state(states, result)
    save_cache(states)
    print(json.dumps({'nodes': [{'id': k, 'ok': v['ok'], 'error': v.get('error'),
        'campaigns': len(v.get('data', {}).get('campaigns', []))} for k, v in states.items()],
        'experiments': [{k: c.get(k) for k in ('method', 'root', 'graded_count', 'expected',
            'active_count', 'failed_count', 'status')} for c in reconcile(states)]}, ensure_ascii=False))
