"""Stable outcome classification including caught agent transport/protocol stops."""
def classify(outcome):
    status=outcome.get('agent_status','') or ''
    if outcome.get('error'): return 'engineering_failure'
    if status in {'visually_accepted','solver_declared_done','solver_declared_fail'}: return 'agent_completed'
    if any(x in status for x in ('budget','limit reached','prediction limit','request limit')): return 'resource_limit'
    if any(x in status for x in ('transport','output','unsupported GUI','controller','planning failed')): return 'engineering_failure'
    if status=='repeated unsupported completion; final obligations unresolved': return 'verification_unresolved'
    return 'unclassified_stop'
