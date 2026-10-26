"""Zero-API replay of every preprojection state in the just-terminated run."""
import json,sys
from pathlib import Path
OLD=Path('/var/tmp/longcli-dh-tools-context-repair-20261008')
ROOT=Path('/var/tmp/longcli-dh-tools-context-repair2-20261008')
sys.path.insert(0,str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.context_budget import fit_payload
paths=list((OLD/'jobs').glob('*/trace/events.jsonl'));systems={}
for path in paths:
    for line in path.open():
        e=json.loads(line)
        if e.get('event')=='final_prompt':systems[e['role']]=e['messages'][0]['content']
total=0;peak=0;errors=[]
for path in paths:
    for line in path.open():
        e=json.loads(line)
        if e.get('event')!='context_source':continue
        try:
            p,s=fit_payload(systems[e['role']],e['payload'],44976)
            assert s['input_bytes']<=44976;peak=max(peak,s['input_bytes']);total+=1
        except Exception as error:
            errors.append({'job':path.parents[1].name,'sequence':e.get('sequence'),
                'error_type':type(error).__name__})
result={'states_replayed':total,'jobs':len(paths),'errors':errors,'peak_input_bytes':peak,
    'includes_failed_preprojection_input':True,'paid_model_calls':0,'passed':not errors}
(ROOT/'evidence/current-context-replay.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result));assert not errors
