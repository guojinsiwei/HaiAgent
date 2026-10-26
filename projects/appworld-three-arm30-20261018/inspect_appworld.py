from appworld import AppWorld,load_task_ids
from appworld.task import Task
from appworld.evaluator import evaluate_task
import inspect,json
from pathlib import Path
print('INIT',inspect.signature(AppWorld))
print('GRADE',inspect.signature(evaluate_task))
print('LOAD',inspect.signature(Task.load))
ids=load_task_ids('test_normal');print('COUNTS',len(ids));print('IDS',ids[:6])
p=Path('/appworld/data/tasks')/ids[0]
print('TASK_FILES',[str(f.relative_to(p)) for f in p.rglob('*')][:30])
print('DATA_DIRS',[f.name for f in Path('/appworld/data').iterdir()])
task=Task.load(ids[0],load_ground_truth=False)
print('TASK_FIELDS',list(task.__dict__))
print('SUPERVISOR_TYPE',type(task.supervisor).__name__)
print('EVALUATOR_SOURCE',inspect.getsource(evaluate_task)[-5000:])
