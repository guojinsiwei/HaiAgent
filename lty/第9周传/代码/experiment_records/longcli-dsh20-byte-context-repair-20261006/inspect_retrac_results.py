"""Bounded public result snapshot; never read credentials or process environments."""
from collections import Counter
import json
from pathlib import Path

root = Path('/var/tmp/lizh639-longcli-retrac20-college-20261006')
summaries = [json.loads(p.read_text()) for p in (root / 'jobs').glob('*/summary.json')]
reports = [json.loads(p.read_text()) for p in (root / 'grades').glob('*/result.json')]
complete = [r for r in reports if r.get('grading_state') == 'complete']
scores = [float(r['f2p']['step_score']) for r in complete]
print(json.dumps({'generation_ended': len(summaries), 'graded': len(complete),
    'stop_reasons': dict(Counter(s.get('stop_reason') for s in summaries)),
    'official_successes': sum(bool(r.get('official_success')) for r in complete),
    'official_f2p_mean': sum(scores) / len(scores) if scores else None,
    'negative_scores': sum(s < 0 for s in scores),
    'tools': sum(s.get('root_tool_dispatches', 0) for s in summaries),
    'requests': sum(s.get('logical_model_requests', 0) for s in summaries),
    'rows': [{'task': s['task'], 'stop': s.get('stop_reason'),
              'tools': s.get('root_tool_dispatches'), 'requests': s.get('logical_model_requests')}
             for s in summaries]}, ensure_ascii=False, indent=2))
