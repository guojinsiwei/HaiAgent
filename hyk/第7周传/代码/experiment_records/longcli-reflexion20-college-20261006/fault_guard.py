"""Pure program-side campaign circuit breaker; never requests a model."""
NORMAL_STOPS = {'evaluator_passed', 'max_trials_reached', 'max_total_seconds_reached',
                'max_model_calls_reached', 'max_tool_calls_reached', 'insufficient_model_calls_for_retry'}


def failure(record, calls=()):
    if record.get('engineering_fault'):
        return record['engineering_fault']
    if record.get('state') == 'engineering_failure':
        return record.get('error_type') or 'engineering_failure'
    if record.get('state') == 'batch_interrupted':
        return 'batch_interrupted'
    if record.get('task_processes_stopped') is False:
        return 'cleanup_failed'
    if any(c.get('status') in (400, 401, 403, 429) for c in calls):
        return 'provider_http_failure'
    reason = record.get('stop_reason')
    if reason and reason not in NORMAL_STOPS:
        return reason
    if record.get('error'):
        return 'reported_run_error'
    if record.get('state') == 'awaiting_grade' and not reason:
        return 'missing_finish_receipt'
    return None


def event_failure(event, payload):
    if event in {'invalid_reflection', 'invalid_evaluation', 'invalid_action'} and payload.get('attempt', 0) >= 2:
        return event + '_repair_exhausted'
    if event == 'run_error':
        return payload.get('phase', 'run') + '_error'
    if event == 'run_end':
        return failure(payload.get('result', payload))
    return None


def canary_passed(records):
    return len(records) == 2 and all(
        not failure(r) and r.get('task_processes_stopped') and r.get('artifact')
        and (r.get('committed_states', 0) >= 1 or r.get('stop_reason') == 'evaluator_passed')
        and r.get('writable_workspace_verified') for r in records)
