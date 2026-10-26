import json
from pathlib import Path
EXPECTED={'schema_version':10,'selection':'original_tb2_sample10_fixed_before_outcomes','task_count':10,'trial_count':20,'concurrency':4,'solver_seconds':7200,'engineering_retry_batches':0,'preflight_attempts_per_trial':1,'retry_score_zero':False,'retry_valid_budget_exhaustion':False}
def load(root):
 c=json.loads((Path(root)/'experiment.json').read_text())
 if c!=EXPECTED:raise ValueError('Frozen experiment contract mismatch')
 return c
def protocol_fields(c):return dict(total_trials=20,max_trials_with_retry=20,paid_attempts_per_arm_task=1,no_automatic_paid_retries=True,task_preflight='One unpaid original-verifier preflight for each run',retry_policy='No automatic paid retries',concurrency={'total':4,'per_arm':2},experiment=c)
def validate_protocol(root):
 c=load(root);p=json.loads((root/'protocol.json').read_text())
 for k,v in protocol_fields(c).items():
  if p.get(k)!=v:raise ValueError('Protocol mismatch: '+k)
 if p['budget']['server_solver_seconds']!=7200:raise ValueError('Wall mismatch')
 names=[t['name'] for t in json.loads((root/'tasks.json').read_text())['tasks']]
 if len(names)!=10 or len(set(names))!=10:raise ValueError('Task selection mismatch')
 return c
