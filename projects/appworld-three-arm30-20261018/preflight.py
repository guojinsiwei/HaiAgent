"""Trusted offline check: starter state persists and all 30 official graders execute."""
import json
from pathlib import Path
from appworld import AppWorld
from appworld.evaluator import evaluate_task
R=Path('/control');tasks=json.loads((R/'task-manifest.json').read_text())['tasks'];rows=[]
for row in tasks:
    task=row['task']
    with AppWorld(task_id=task,experiment_name='preflight',load_ground_truth=False,timeout_seconds=60) as world:
        out=world.execute('print(apis.api_docs.show_app_descriptions())')
        assert 'supervisor' in out,out[:300]
    result=evaluate_task(task_id=task,experiment_name='preflight',suppress_errors=True)
    report={'success':result.success,'pass_count':result.pass_count,'total_count':result.total_count};rows.append({'task':task,'report':report})
    (R/'grading-preflight.json').write_text(json.dumps(rows,indent=2,default=str))
    print(task,json.dumps(report,default=str),flush=True)
print('ALL_30_STARTER_GRADERS_EXECUTED',flush=True)
