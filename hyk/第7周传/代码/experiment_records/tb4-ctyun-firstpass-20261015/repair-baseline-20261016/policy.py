"""Explicit score-based stopping; engineering completion is reported separately."""
def passed(result):
    rewards=(result.get('verifier_result') or {}).get('rewards') or {}
    return not result.get('exception_info') and rewards.get('reward') == 1

def summarize(result):
    return dict(passed=passed(result),reward=((result.get('verifier_result') or {}).get('rewards') or {}).get('reward'),
                exception_type=(result.get('exception_info') or {}).get('exception_type'))
