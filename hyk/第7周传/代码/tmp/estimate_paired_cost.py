import json
import re
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

root = Path('/mnt/lizh639/bestfgs-runs/swe100-paired-v2')
fields = ('prompt_tokens', 'cached_prompt_tokens', 'cache_miss_prompt_tokens', 'completion_tokens', 'api_requests', 'api_responses', 'usage_missing_responses')
report = {'as_of': datetime.now(timezone.utc).isoformat(), 'methods': {}}
for method in ('bestfgs', 'raw'):
    states = [json.loads(path.read_text()) for path in (root / method / 'states').glob('*.json')]
    total = Counter()
    rows = []
    for state in states:
        ended = state.get('status') == 'completed'
        current = state.get('model_usage', {})
        prior = state.get('previous_attempts', [])
        for value in ([state] if current else []) + prior:
            total.update({k: value.get('model_usage', {}).get(k, 0) for k in fields})
        if ended:
            rows.append({'id': state['id'], 'stop_reason': state.get('stop_reason'), 'attempt_count': state.get('attempt_count', 1),
                         'usage': current, 'previous_usage': [v.get('model_usage', {}) for v in prior]})
    # Running attempts have no final usage summary; request usage logs expose input
    # cache counts, but NOT output tokens. Never invent missing output usage.
    running_input = Counter()
    for state in states:
        if state.get('status') != 'running':
            continue
        identity = state['id']
        child_path = root / method / 'search' / identity / identity / 'status.json'
        if not child_path.is_file():
            continue
        child = json.loads(child_path.read_text())
        log = Path(child['attempt']) / 'agent.log'
        if log.is_file():
            for p, hit, miss in re.findall(r'输入=(\d+)，命中=(\d+)，未命中=(\d+)', log.read_text(errors='replace')):
                running_input.update(prompt_tokens=int(p), cached_prompt_tokens=int(hit), cache_miss_prompt_tokens=int(miss))
    report['methods'][method] = {'states': dict(Counter(s['status'] for s in states)),
                                 'ended_and_prior_usage': dict(total), 'running_input_only': dict(running_input), 'completed_rows': rows}
print(json.dumps(report, ensure_ascii=False))
