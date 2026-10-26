"""Explicit score-based stopping; engineering completion is reported separately."""
def passed(result):
    rewards=(result.get('verifier_result') or {}).get('rewards') or {}
    return not result.get('exception_info') and rewards.get('reward') == 1

def summarize(result):
    return dict(passed=passed(result),reward=((result.get('verifier_result') or {}).get('rewards') or {}).get('reward'),
                exception_type=(result.get('exception_info') or {}).get('exception_type'))

PROVIDER_FAILURES = {'credentials','quota','refusal','invalid_request','protocol',
                     'transport','accounting','temporary_exhausted','budget'}

def outcome(info, stderr=''):
    """Keep the official reward untouched; classify why the attempt ended."""
    if info.get('passed'):return 'passed'
    if info.get('exception_type'):return 'infrastructure_error'
    kind = (info.get('provider') or {}).get('kind')
    # Legacy provider-state could incorrectly say available after a fatal error.
    if kind == 'refusal' or ('INVALID_REQUEST' in stderr and '很抱歉' in stderr):return 'provider_refusal'
    if kind in PROVIDER_FAILURES - {'budget'}:return 'provider_' + kind
    stop=(info.get('budget_stop') or {}).get('reason') or (info.get('provider') or {}).get('reason')
    if stop in ('usage_unavailable','unsettled_requests_after_restart','usage_exceeds_model_ceiling'):return 'accounting_interrupted'
    if stop and stop.startswith('provider_') and stop!='provider_budget':return 'peer_provider_interrupted'
    if info.get('budget_stop') or kind == 'budget':return 'budget_interrupted'
    if 'MALFORMED_RESPONSE' in stderr:return 'provider_protocol'
    if 'INVALID_REQUEST' in stderr:return 'provider_invalid_request'
    if 'PROVIDER_UNAVAILABLE' in stderr:return 'provider_error'
    solver = info.get('solver_exit') or {}
    if solver.get('timed_out'):return 'solver_timeout'
    if solver.get('exit_code') not in (None, 0):return 'solver_error'
    if solver.get('exit_code') is None:return 'execution_unverified'
    return 'answer_failed' if info.get('reward') is not None else 'grading_unavailable'

def completion_halt(info):
    state = info.get('outcome') or outcome(info)
    if state == 'passed':return 'first_official_pass'
    if state == 'budget_interrupted':return (info.get('budget_stop') or {}).get('reason','provider_budget')
    if state != 'answer_failed':return state
    return None
