"""Interpret terminal events, not reward magnitude. No model-policy changes."""
def classify(result, events):
    reasons = []
    endings = [e for e in events if e.get('event') == 'method_end']
    stop = None
    if endings:
        end = endings[-1]
        stop = end.get('stop_reason') or (end.get('result') or {}).get('stop_reason')
    deadline = stop in {'wall_budget', 'wall_budget_exhausted'}
    exception = result.get('exception_info') or {}
    if exception and exception.get('exception_type') != 'AgentTimeoutError':
        reasons.append('official_exception:' + str(exception.get('exception_type')))
    if result.get('process_exit_code') != 0:
        reasons.append('worker_exit_nonzero')
    if result.get('verifier_result') is None:
        reasons.append('missing_official_verifier')
    if any(e.get('event') == 'adapter_error' for e in events):
        reasons.append('adapter_error')
    # Only the final model error immediately before an explicit deadline ending
    # is tolerated. Earlier errors/auth failures remain actionable.
    errors = []
    for i, event in enumerate(events):
        if event.get('event') != 'model_error':
            continue
        following = events[i+1:i+2]
        deferred = (event.get('role') == 'memory' and event.get('failure_kind') == 'model_output'
                    and following and following[0].get('event') == 'memory_update_deferred')
        if not deferred:
            errors.append(i)
    if errors:
        after = events[errors[-1]+1:]
        adjacent = bool(after) and after[0].get('event') == 'method_end'
        if not (deadline and len(errors) == 1 and adjacent):
            reasons.append('model_error')
    return {'stop_reason': stop, 'infrastructure_ok': not reasons, 'reasons': reasons}
