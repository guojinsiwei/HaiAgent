"""Generate new explicit protocol and redacted historical wire regression fixtures."""
import json
from pathlib import Path
from common import ROOT,save

old=ROOT.parent/'longcli-v6-raw-paired10-20261001'
p=json.loads((ROOT/'previous-protocol.json').read_text(encoding='utf-8'))
p.update(experiment='longcli-threeway-engineering-20261003',methods=['bestfgs-v6.1','orthogonal-v8','raw'],
    total_trials=30,workers=2,assignment='Rotating method order, 15 fresh jobs per worker',
    response_protocol='one shared strict JSON wire; actor/adviser at most 2 attempts, monitor 1; no substring salvage',
    original_task_inputs_identical=True,prior_results_carried=0,
    source_releases={'bestfgs-v6.1':'monitor-control-v6.1','orthogonal-v8':'contrastive-engineering-repair-v2/orthogonal',
                     'raw':'monitor-control-v6.1 HAI method=raw with common wire'},
    grading_storage_floor_disabled=True,status='preparing_not_started')
p.pop('created',None);p['created_date']='2026-10-03'
p['context_windows']['orthogonal-v8']='48000 characters, native budgeted dialogue and memory'
p['grading_resources'].update(concurrency=1,disk_reserve_gib=None)
save(ROOT/'protocol.json',p)
cases=[]
for job in sorted((old/'received').glob('raw--*')):
    generation=json.loads((job/'generation-summary.json').read_text(encoding='utf-8'))
    if generation['stop_reason']!='protocol_error':continue
    events=[json.loads(s) for s in (job/'model-audit.jsonl').read_text(encoding='utf-8').splitlines()]
    for event in events:
        if event.get('event')!='model_response':continue
        content=(event.get('response') or {}).get('content')
        if not isinstance(content,str):continue
        try:value=json.loads(content)
        except ValueError:value=None
        if not isinstance(value,dict):
            cases.append(dict(job=job.name,content=content,source='previous redacted model-audit.jsonl'));break
assert len(cases)==9,'Need every one of the nine prior protocol-limited tasks'
save(ROOT/'historical-wire-failures.json',cases)
print(json.dumps(dict(historical_failure_cases=9,model_calls=0,total_authorized_trials=30)))
