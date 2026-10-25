"""Interpret terminal events, not reward magnitude. No model-policy changes."""
def classify(result, events):
    if result.get('method') == 'hai':
        from hai_outcomes import classify as classify_hai
        return classify_hai(result, events)
    infrastructure_reasons = []
    method_issues = []
    endings = [e for e in events if e.get('event') == 'method_end']
    stop = result.get('stop_reason')
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
    if stop in {'infrastructure_error', 'delivery_error'}:
        infrastructure_reasons.append('infrastructure_stop')
    # Only the final model error immediately before an explicit deadline ending
    # is tolerated. Earlier errors/auth failures remain actionable.
    errors = [i for i,e in enumerate(events) if e.get('event') == 'model_error']
    # A successful response from the SAME role proves the request stream recovered.
    # Preserve every error count; recovery cannot excuse a fatal provider status
    # or a terminal method failure. Advisor responses cannot recover actor errors.
    later_roles, recovered = set(), set()
    for i in range(len(events)-1, -1, -1):
        event = events[i]
        if event.get('event') == 'model_response':
            later_roles.add(event.get('role'))
        elif event.get('event') == 'model_error':
            code = str(event.get('error_code') or '')
            fatal = code in {'http_400', 'http_401', 'http_402', 'http_403',
                            'provider_400', 'provider_401', 'provider_402', 'provider_403'}
            if event.get('role') is not None and event.get('role') in later_roles and not fatal:
                recovered.add(i)
    unresolved = [i for i in errors if i not in recovered]
    optional_errors = [i for i in unresolved if events[i].get('role') == 'monitor']
    required_unresolved = [i for i in unresolved if i not in optional_errors]
    tolerated_deadline = False
    if errors:
        after = [e for e in events[errors[-1]+1:] if e.get('event') != 'mechanism_utilization']
        adjacent = bool(after) and after[0].get('event') == 'method_end'
        tolerated_deadline = deadline and len(unresolved) == 1 and adjacent and not events[errors[-1]].get('error_code')
    if (required_unresolved and not tolerated_deadline) or stop in {
            'model_error', 'api_error', 'credential_or_balance_error'}:
        method_issues.append('model_error')
    if stop == 'model_or_protocol_error_limit':
        method_issues.append('contrastive_gate_limit' if result.get('contrastive_gate_limit') else 'model_or_protocol_limit')
    return {'stop_reason': stop, 'infrastructure_ok': not infrastructure_reasons,
            'reasons': infrastructure_reasons, 'method_issues': method_issues,
            'model_error_count': len(errors), 'recovered_model_errors': len(recovered),
            'unrecovered_model_errors': len(unresolved),
            'optional_monitor_errors': len(optional_errors),
            'warnings': (['recovered_model_errors'] if recovered else []) +
                        (['optional_monitor_errors'] if optional_errors else [])}
