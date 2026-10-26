"""Trusted TRAIN-only official solutions validate positive scoring; no agent sees them."""
from appworld import AppWorld,load_task_ids
from pathlib import Path
import json
rows=[]
for task in load_task_ids('train')[:3]:
    with AppWorld(task_id=task,experiment_name='positive-control',ground_truth_mode='full',raise_on_failure=False) as world:
        world.execute(world.task.ground_truth.compiled_solution_code+'\nsolution(apis, requester)')
        tracker=world.evaluate();rows.append({'task':task,'success':tracker.success,'pass_count':tracker.pass_count,'total_count':tracker.total_count})
    assert rows[-1]['success'],rows[-1]
Path('/control/positive-control.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))
