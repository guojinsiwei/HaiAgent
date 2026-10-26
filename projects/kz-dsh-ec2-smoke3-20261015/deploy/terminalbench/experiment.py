"""One source for the frozen queue contract and its protocol description."""
import json
from pathlib import Path


def load(root):
    config = json.loads((Path(root)/'experiment.json').read_text())
    # This engineering revision cannot silently change the experimental design.
    expected = dict(schema_version=1, selection='first_3_of_frozen_30', task_count=3,
                    concurrency=1, solver_seconds=10800, engineering_retry_batches=1,
                    preflight_attempts_per_trial=1, retry_score_zero=False,
                    retry_valid_budget_exhaustion=False)
    if config != expected or any(type(config[k]) is not type(v) for k,v in expected.items()):
        raise ValueError('Unsupported experiment contract; explicit design revision required')
    return config


def protocol_fields(config):
    return dict(total_trials=config['task_count'], max_trials_with_retry=config['task_count']*2,
                paid_attempts_per_arm_task=2, no_automatic_paid_retries=False,
                task_preflight='One unpaid preflight per trial; one final engineering-fault retry batch.',
                retry_policy='finish first pass; one final engineering-fault-only retry batch; no score-zero or valid wall-budget retries',
                concurrency={'total':config['concurrency'],'per_arm':config['concurrency']},
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
