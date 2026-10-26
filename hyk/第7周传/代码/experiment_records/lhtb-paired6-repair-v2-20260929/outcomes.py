"""Interpret terminal events, not reward magnitude. No model-policy changes."""
def classify(result, events):
    if result.get('method') == 'hai':
        from hai_outcomes import classify as classify_hai
        return classify_hai(result, events)
    infrastructure_reasons = []
    method_issues = []
    endings = [e for e in events if e.get('event') == 'method_end']
    stop = None
    if endings:
        end = endings[-1]
        stop = end.get('stop_reason') or (end.get('result') or {}).get('stop_reason')
    deadline = stop in {'wall_budget', 'wall_budget_exhausted'}
    exception = result.get('exception_info') or {}
    if exception and exception.get('exception_type') != 'AgentTimeoutError':
        infrastructure_reasons.append('official_exception:' + str(exception.get('exception_type')))
    if result.get('process_exit_code') != 0:
        infrastructure_reasons.append('worker_exit_nonzero')
    if result.get('verifier_result') is None:
        infrastructure_reasons.append('missing_official_verifier')
    if any(e.get('event') == 'adapter_error' for e in events):
        infrastructure_reasons.append('adapter_error')
    if stop == 'infrastructure_error':
        infrastructure_reasons.append('infrastructure_stop')
    # Only the final model error immediately before an explicit deadline ending
    # is tolerated. Earlier errors/auth failures remain actionable.
    errors = [i for i,e in enumerate(events) if e.get('event') == 'model_error']
    if errors:
        after = [e for e in events[errors[-1]+1:] if e.get('event') != 'mechanism_utilization']
        adjacent = bool(after) and after[0].get('event') == 'method_end'
        if not (deadline and len(errors) == 1 and adjacent and not events[errors[-1]].get('error_code')):
            method_issues.append('model_error')
    return {'stop_reason': stop, 'infrastructure_ok': not infrastructure_reasons,
            'reasons': infrastructure_reasons, 'method_issues': method_issues}
