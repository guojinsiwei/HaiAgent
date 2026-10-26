"""Promote completed pilot ledger without replaying any attempted job."""
import json
from pathlib import Path
import time
from control import HERE,validate
from prepare import write

validate()
scope=json.loads((HERE/'run-scope.json').read_text())
if scope['stage']=='screen':
    print(json.dumps(dict(stage='screen',already_promoted=True)))
else:
    health=json.loads((HERE/'health.json').read_text())
    if (health.get('stage')!='pilot' or health.get('completed')!=10 or health.get('active')
            or health.get('state') not in {'completed','completed_with_errors'} or health.get('problems')):
        raise RuntimeError('Pilot must finish all ten trials before promotion')
    if any(r.get('admission_failure') for r in health.get('trial_issues',[])):
        raise RuntimeError('Resolve pilot engineering failures before expanding')
    write(HERE/'run-scope.json',dict(stage='screen',promoted_at=time.time(),pilot_trials=10))
    print(json.dumps(dict(stage='screen',total=120,existing_pilot_trials=10,new_trials=110)))
