"""One source for the frozen queue contract and its protocol description."""
import json
from pathlib import Path


def load(root):
    config = json.loads((Path(root)/'experiment.json').read_text())
    # This engineering revision cannot silently change the experimental design.
    expected = dict(schema_version=8, selection='tb2_pure_dsh_authorized_transport_repair_one', task_count=1, trial_count=1,
                    concurrency=1, solver_seconds=2700, engineering_retry_batches=0,
                    preflight_attempts_per_trial=1, retry_score_zero=False,
                    retry_valid_budget_exhaustion=False)
    if config != expected or any(type(config[k]) is not type(v) for k,v in expected.items()):
        raise ValueError('Unsupported experiment contract; explicit design revision required')
    return config


def protocol_fields(config):
    return dict(total_trials=config['trial_count'], max_trials_with_retry=config['trial_count'],
                paid_attempts_per_arm_task=1, no_automatic_paid_retries=True,
                task_preflight='One unpaid preflight per trial; no paid retry batch.',
                retry_policy='one pass only; no automatic paid retries',
                concurrency={'total':config['concurrency'],'per_arm':1},
                experiment=config)


def validate_protocol(root):
    config=load(root)
    protocol=json.loads((Path(root)/'protocol.json').read_text())
    expected=protocol_fields(config)
    for key,value in expected.items():
        if protocol.get(key)!=value:
            raise ValueError('Protocol disagrees with experiment.json: '+key)
    if protocol.get('budget',{}).get('server_solver_seconds')!=config['solver_seconds']:
        raise ValueError('Solver deadline disagrees with experiment.json')
    tasks=json.loads((Path(root)/'tasks.json').read_text())['tasks']
    if len(tasks)!=config['task_count'] or len({t['name'] for t in tasks})!=len(tasks):
        raise ValueError('Task manifest disagrees with frozen selection')
    return config
