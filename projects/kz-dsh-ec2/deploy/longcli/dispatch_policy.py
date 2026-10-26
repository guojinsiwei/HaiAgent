"""Offline-testable scheduling policy. No retries, keys, Docker or API access."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter


def disposition(result):
    # Official score must NEVER erase a runtime/cleanup failure.
    fault = result.get('engineering_fault')
    if not fault:
        return 'continue' if result.get('state') == 'graded' else 'pause'
    if (fault == 'tool_json_retries_exhausted'
            and result.get('grading_state') == 'complete'
            and result.get('container_destroyed') is True):
        return 'isolate'
    return 'pause'  # auth/config/disk/unknown/grader/cleanup failures


def dispatch_trials(rows, trial, publish, concurrency=2):
    """One pilot, then bounded dispatch; never automatically repeat any row.

    A single classified JSON task failure is isolated. Two such failures in
    this campaign stop NEW dispatch as a possible shared provider fault.
    Already-running unrelated tasks drain and retain their artifacts.
    """
    if concurrency < 1:
        raise ValueError('concurrency must be positive')
    rows = list(rows)
    if len({r['task'] for r in rows}) != len(rows):
        raise ValueError('duplicate task would duplicate paid execution')
    results, pending, counts = [], list(rows), Counter()
    pause_reason = None

    def accept(result):
        nonlocal pause_reason
        results.append(result)
        action = disposition(result)
        if action == 'pause':
            pause_reason = result.get('engineering_fault', 'unclassified_task_state')
        elif action == 'isolate':
            counts[result['engineering_fault']] += 1
            if counts[result['engineering_fault']] >= 2:
                pause_reason = 'repeated_tool_json_failures'

    def snapshot(active=()):
        state = ('paused_draining' if active else 'needs_attention') if pause_reason else (
            'running' if active or pending else ('complete_with_errors' if any(disposition(r) == 'isolate' for r in results) else 'complete'))
        value = dict(state=state, results=list(results), active=list(active),
                     pending=[r['task'] for r in pending], pause_reason=pause_reason)
        publish(value)
        return value

    def invoke(row):
        try:
            return trial(row)
        except Exception as error:
            # Do not log arbitrary exception strings (may include credentials).
            return dict(task=row['task'], state='needs_attention',
                        engineering_fault='worker_exception', error_type=type(error).__name__)

    if pending:
        pilot = pending.pop(0)
        snapshot([pilot['task']])
        accept(invoke(pilot))
        snapshot()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        active = {}
        while active or (pending and not pause_reason):
            while pending and not pause_reason and len(active) < concurrency:
                row = pending.pop(0)
                active[pool.submit(invoke, row)] = row['task']
            snapshot(active.values())
            finished, _ = wait(active, timeout=10, return_when=FIRST_COMPLETED)
            for future in finished:
                active.pop(future)
                accept(future.result())
        return snapshot()


def terminal_fault(exit_code, stderr, existing=None, recovery_exhausted=False):
    if existing:
        return existing
    if exit_code == 0:
        return None
    if (recovery_exhausted
            and 'MALFORMED_RESPONSE: DeepSeek Messages stream: tool input is invalid JSON' in stderr):
        return 'tool_json_retries_exhausted'
    return 'native_error_inspect_logs'
