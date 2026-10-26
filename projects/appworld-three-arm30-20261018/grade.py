"""Official grading, only after the solver stops, never visible to agents."""
import json,sys
from pathlib import Path
from appworld.evaluator import evaluate_task
task=sys.argv[1]
result=evaluate_task(task_id=task,experiment_name='trial',suppress_errors=True)
report={'success':result.success,'pass_count':result.pass_count,'total_count':result.total_count,'details':result.to_dict()}
Path('/result/result.json').write_text(json.dumps(report,indent=2,default=str))
print(json.dumps(report,default=str))
