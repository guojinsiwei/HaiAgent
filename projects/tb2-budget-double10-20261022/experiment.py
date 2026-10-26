import json
from pathlib import Path
def validate_protocol(root):
 r=Path(root);s=json.loads((r/'selection.json').read_text());p=json.loads((r/'protocol.json').read_text());c=json.loads((r/'experiment.json').read_text())
 assert len(s['rows'])==10 and len({x['job'] for x in s['rows']})==10
 assert p['total_trials']==10 and p['max_trials_with_retry']==10 and p['no_automatic_paid_retries']
 assert p['budget']['per_run_cny']==16 and p['budget']['campaign_cny']==160
 assert p['budget']['shared_requests']==800 and p['budget']['shared_tools']==1200
 assert p['budget']['server_solver_seconds']==7200 and c==p['experiment']
 assert p['concurrency']['total']==6
 return c
