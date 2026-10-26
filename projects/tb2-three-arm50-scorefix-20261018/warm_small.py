from warm_dependencies import one
import json
for task in ['mteb-leaderboard','largest-eigenval','hf-model-inference','make-mips-interpreter','train-fasttext']:
 try:print(json.dumps(one(task)),flush=True)
 except Exception as e:print(json.dumps(dict(task=task,error=str(e))),flush=True)
