"""Read-only compact progress, without prompts, credentials or process environments."""
from collections import Counter
import json
from pathlib import Path

root = Path(__file__).resolve().parent
def read(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
def lines(path):
    if not path.exists(): return []
    result = []
    for line in path.read_text().splitlines():
        try: result.append(json.loads(line))
        except json.JSONDecodeError: pass
    return result

report = {'status': read(root / 'retry2-status.json')}
trials = list((root / 'jobs/taotoken-smoke-retry2').glob('*/agent'))
if trials:
    agent = trials[0]
    report['trial'] = agent.parent.name
    report['live_gate'] = read(agent / 'live-gate-result.json')
    wire = lines(agent / 'task-run/request-route.jsonl')
    events = lines(agent / 'task-run/dsh.jsonl')
    requests = [e for e in wire if e.get('event') == 'request']
    report['requests'] = len(requests)
    report['http_statuses'] = dict(Counter(str(e.get('status')) for e in wire if e.get('event') == 'response'))
    report['route_integrity'] = bool(requests) and all(e.get('endpointMatches') and e.get('keyMatchesInput') for e in requests)
    report['tool_calls'] = dict(Counter(e.get('tool') for e in events if e.get('type') == 'tool_call'))
    report['tool_results'] = dict(Counter(e.get('status') for e in events if e.get('type') == 'tool_result'))
    report['last_wire_time'] = wire[-1].get('time') if wire else None
    report['agent_exit'] = read(agent / 'agent-exit.json')
    try:
        audit=[e for p in (agent/'task-run/kz-audit').glob('*.jsonl') for e in lines(p)]
        report['request_roles']=dict(Counter(e.get('role') for e in audit if e.get('event')=='request_admitted'))
        report['compaction_completed_requests']=sum(e.get('event')=='request_completed' and e.get('role')=='compaction' and e.get('completed') is True for e in audit)
        if any(e.get('event')=='budget_exhausted' for e in audit):
            report['observed_termination']='shared_request_budget_exhausted' if len(requests)>=40 else 'shared_budget_exhausted'
    except PermissionError:
        report['audit_detail']='Container-owned audit unavailable until artifact collection; wire counts remain readable.'
    trial_result = read(agent.parent / 'result.json')
    if trial_result:
        report['verifier_result'] = trial_result.get('verifier_result')
        report['exception_type'] = (trial_result.get('exception_info') or {}).get('exception_type')
print(json.dumps(report, indent=2))
