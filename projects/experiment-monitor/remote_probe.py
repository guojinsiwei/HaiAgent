"""Read-only, stdlib-only remote collector. Emit allowlisted progress metadata."""
import base64
import datetime
import json
import os
from pathlib import Path
import sys
import time

MAX_JSON = 3_000_000


def read(path):
    try:
        if path.stat().st_size > MAX_JSON:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def process_alive(pid, root=None):
    if not isinstance(pid, int) or pid < 2:
        return False
    p = Path('/proc') / str(pid)
    try:
        if p.stat().st_uid != os.getuid() or p.joinpath('stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
            return False
        if root is not None:
            # Reject reused PIDs from unrelated tasks without emitting command lines.
            args = p.joinpath('cmdline').read_bytes()
            cwd = str(p.joinpath('cwd').resolve())
            return str(root).encode() in args or cwd == str(root) or cwd.startswith(str(root) + '/')
        return True
    except (OSError, IndexError):
        return False


def number(record, *keys):
    for key in keys:
        value = record.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def report_fields(path):
    r = read(path)
    if r.get('grading_state') != 'complete':
        return None
    score = r.get('f2p', {}).get('step_score')
    return {'score': score if isinstance(score, (int, float)) else None,
            'official_success': r.get('official_success'), 'report': str(path)}


def public_error(value):
    # Only class/code fields, never exception bodies, prompts or credentials.
    if isinstance(value, dict):
        return {k: str(value[k])[:160] for k in ('job', 'task', 'reason', 'error_type') if k in value}
    return {'reason': 'unknown_error'}


def collect_root(root, node_id, now):
    protocol = read(root / 'protocol.json')
    health = read(root / 'health.json')
    if not protocol or not (health or (root / 'jobs').is_dir()):
        return []
    plan = read(root / 'resume-plan.json') or read(root / 'recovery-plan.json')
    grading = read(root / 'grading-health.json')
    methods = protocol.get('methods') or [plan.get('method')]
    methods = [m for m in methods if isinstance(m, str) and m]
    if not methods:
        return []
    try:
        created = number(plan, 'time') or number(health, 'started') or (root / 'protocol.json').stat().st_mtime
    except OSError:
        created = 0
    output = []
    for method in methods:
        rows = [r for r in protocol.get('tasks', []) if isinstance(r, dict) and isinstance(r.get('task'), str)]
        preserved = plan.get('preserved') or plan.get('reused_scored') or []
        by_task = {r['task']: dict(r) for r in rows}
        for r in preserved:
            if isinstance(r, dict) and r.get('task'):
                by_task.setdefault(r['task'], {'task': r['task']})
        # Include delivered reports not present in a narrowed recovery plan.
        grade_paths = {p.parent.name.split('--', 1)[-1]: p for p in (root / 'grades').glob(method + '--*/result.json')}
        for task in grade_paths:
            by_task.setdefault(task, {'task': task})
        inherited = {}
        for r in preserved:
            if not isinstance(r, dict) or not r.get('task'):
                continue
            path = r.get('report')
            # Preserved pointers must stay inside the user's experiment locations.
            if isinstance(path, str) and path.startswith(('/mnt/lizh639/', '/mnt/sdb/home/lizh639/', '/var/tmp/lizh639-')):
                value = report_fields(Path(path))
                if value:
                    inherited[r['task']] = value
        tasks = []
        for task, row in by_task.items():
            if '/' in task or '..' in task:
                continue
            job = method + '--' + task
            d = root / 'jobs' / job
            live = read(d / 'health.json')
            summary = read(d / 'summary.json')
            r = summary or live
            report = report_fields(grade_paths[task]) if task in grade_paths else inherited.get(task)
            alive = process_alive(live.get('pid'), root)
            interrupted = (d / 'interruption.json').exists()
            fault = r.get('engineering_fault') or r.get('cleanup_error')
            updated = number(r, 'updated', 'ended', 'started')
            age = max(0, now - updated) if updated else None
            if report:
                state = 'graded'
            elif alive:
                state = 'running' if age is None or age < 660 else 'stalled'
            elif live.get('remote_verified_alive') and age is not None and age < 90:
                state = 'running'
            elif interrupted or r.get('state') == 'interrupted':
                state = 'interrupted'
            elif fault or r.get('state') == 'engineering_failure':
                state = 'failed'
            elif r.get('state') == 'awaiting_grade' and (d / 'final-source.tar.gz').exists():
                state = 'awaiting_grade'
            elif interrupted:
                state = 'interrupted'
            elif r and r.get('state') in ('running', 'preparing', 'batch_interrupted'):
                state = 'stopped'
            elif task in inherited:
                state = 'graded'
            else:
                state = 'pending'
            wall = row.get('wall_seconds') or protocol.get('wall_seconds') or 7200
            started = number(r, 'solving_started', 'started')
            ended = number(r, 'ended')
            seconds = number(r, 'seconds')
            if seconds is None and started:
                seconds = max(0, (ended or now) - started)
            tasks.append({'task': task, 'job': job, 'state': state, 'alive': alive,
                'updated': updated, 'age': age, 'started': started, 'seconds': seconds,
                'wall_seconds': wall,
                'models': number(r, 'model_requests', 'logical_model_requests', 'model_calls', 'api_attempts'),
                'wire': number(r, 'actual_api_attempts', 'api_attempts'),
                'model_limit': protocol.get('max_turns', 800),
                'tools': number(r, 'tool_calls', 'root_tool_dispatches'),
                'tool_limit': protocol.get('max_tools', 600),
                'stop_reason': str(r.get('stop_reason') or '')[:100],
                'fault': str(fault or '')[:120],
                'score': report.get('score') if report else None,
                'official_success': report.get('official_success') if report else None,
                'source': str(root), 'node': node_id})
        controller = process_alive(health.get('pid'), root)
        # Relayed TACO grading has a separate launch receipt.
        launch = read(root / 'grading-launch.json') or read(root / 'relay-grader-launch.json')
        grader = process_alive(launch.get('pid'), root)
        errors = health.get('errors') or []
        if isinstance(errors, dict):
            errors = [{'job': k, 'reason': v} for k, v in errors.items()]
        gerrors = grading.get('errors') or []
        if isinstance(gerrors, dict):
            gerrors = [{'job': k, 'reason': v} for k, v in gerrors.items()]
        output.append({'id': node_id + '|' + str(root) + '|' + method,
            'node': node_id, 'root': str(root), 'method': method, 'created': created,
            'cohort': str(plan.get('source') or root), 'tasks': tasks,
            'expected': max(len(by_task), 20 if method in ('lats', 'taco', 'retrac', 'dh', 'recuris_frozen') else len(by_task)),
            'controller_alive': controller, 'grader_alive': grader,
            'raw_state': health.get('state'), 'updated': number(health, 'updated'),
            'grading_state': grading.get('state'), 'errors': [public_error(e) for e in errors],
            'grading_errors': [public_error(e) for e in gerrors],
            'model': protocol.get('model', ''),
            'output_tokens': protocol.get('max_tokens', 4096),
            'preserved_declared': len(preserved), 'observed_at': now})
    return output


def candidates(config):
    roots = {Path(p) for p in config.get('roots', [])}
    for location in config.get('locations', []):
        parent = Path(location['parent'])
        try:
            for p in parent.iterdir():
                if p.is_dir() and any(p.name.startswith(s) for s in location['prefixes']):
                    roots.add(p)
        except OSError:
            pass
    # Bounded one-level discovery for umbrella recovery campaigns.
    for root in list(roots):
        if (root / 'protocol.json').exists():
            continue
        try:
            roots.update(p for p in root.iterdir() if p.is_dir() and (p / 'protocol.json').exists())
        except OSError:
            pass
    # Prefer live/new roots, but keep completed experiments available as history.
    return sorted(roots, key=lambda p: (p / 'protocol.json').stat().st_mtime if (p / 'protocol.json').exists() else 0,
                  reverse=True)[:200]


def main():
    config = json.loads(base64.b64decode(sys.argv[1]))
    now = time.time()
    campaigns = []
    for root in candidates(config):
        try:
            campaigns.extend(collect_root(root, config['id'], now))
        except (OSError, ValueError, TypeError, KeyError):
            # One incomplete atomic receipt must not erase other experiments.
            continue
    print(json.dumps({'node': config['id'], 'observed_at': now,
        'remote_time': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'campaigns': campaigns}, ensure_ascii=False))


if __name__ == '__main__':
    main()
