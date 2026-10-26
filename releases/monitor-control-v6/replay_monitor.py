"""Read-only replay of all twelve frozen trajectories; no execution or model calls.

Checks input reachability and schedule coverage, NOT hypothetical model decisions.
Historical pipeline statuses cannot be reconstructed and are never fabricated.
"""
from collections import OrderedDict,Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.monitor_context import build_context,schedule
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_monitor import MONITOR_SYSTEM

def main():
    old=Path(sys.argv[1])
    rows=json.loads((old/'summary.json').read_text())
    results=[]
    for trial in rows:
        path=Path(trial['report']).parent/'agent/method/events.jsonl'
        raw=path.read_bytes();events=[json.loads(s) for s in raw.splitlines()]
        head=events[0];current={};scope='unknown'
        r=SimpleNamespace(task=SimpleNamespace(goal=head['task']['goal'],constraints=head['task']['constraints']),
            config=replace(LeanConfig(**head['config']),monitor_reliability=True),
            evidence=OrderedDict(),memory_pending=OrderedDict(),memory=SimpleNamespace(items=OrderedDict()),
            monitor_review={},progress=SimpleNamespace(view=lambda:current),
            environment=SimpleNamespace(scope=lambda:scope),counts=Counter(),monitor_lanes=Counter(),
            monitor_event=None,started_at=time.monotonic(),control_view=lambda:{})
        passed=failed=0;diagnostics=[];scheduled=[];last=0;last_tool=None
        old_triggers=0
        for e in events:
            if e['event']=='model_request' and e['role']=='action':
                current=e['payload']['fixed_context']['delivery_progress']
            elif e['event']=='conversation_turn' and 'evidence' in e.get('feedback',{}):
                row=e['feedback']['evidence'];r.evidence[row['id']]=row;scope=row['after']
                while len(r.evidence)>48:r.evidence.popitem(last=False)
                r.counts['tool_calls']=int(row['id'][1:])
                r.started_at=time.monotonic()-max(0,e['time']-head['time'])
                r.monitor_event='failure_cluster' if row['return_code']!=0 else None
                n=r.counts['tool_calls']
                if n-last>=r.config.monitor_cooldown_tools and n<r.config.max_tools:
                    decision=schedule(r)
                    if decision:
                        lane,reason=decision
                        payload,d=build_context(r,reason,r.config.monitor_context_chars-len(MONITOR_SYSTEM)-1024)
                        scheduled.append(dict(tool=n,lane=lane,context_chars=d['chars']))
                        r.monitor_lanes[lane]+=1;last=n
            elif e['event']=='memory_admitted':
                item=e['memory'];r.memory.items[item['id']]=item
            elif e['event']=='memory_evicted':
                r.memory.items.pop(e.get('memory_id',e.get('id')),None)
            elif e['event']=='monitor_review':r.monitor_review=e
            elif e['event']=='monitor_trigger':
                old_triggers+=1
                try:
                    p,d=build_context(r,e['trigger'],r.config.monitor_context_chars-len(MONITOR_SYSTEM)-1024)
                    assert len(p['evidence'])>=2
                    passed+=1;diagnostics.append(d)
                except (ValueError,AssertionError):failed+=1
        result=dict(task=trial['task'],source_path=str(path),source_sha256=hashlib.sha256(raw).hexdigest(),
            old_triggers=old_triggers,context_build_passed=passed,context_build_failed=failed,
            max_context_chars=max(d['chars'] for d in diagnostics),
            min_evidence_count=min(d['evidence_count'] for d in diagnostics),
            simulated_schedule=scheduled,
            covers_last_tenth=bool(scheduled and scheduled[-1]['tool']>=r.config.max_tools*.9),
            historical_outcomes_not_reexecuted=True,model_calls=0)
        results.append(result);print(json.dumps(result),flush=True)
    report=dict(tasks=results,success=len(results)==12 and all(x['context_build_failed']==0 and x['covers_last_tenth']
        and len(x['simulated_schedule'])<=12 for x in results),model_calls=0,
        limitation='Input/schedule replay only; no claim about real model judgments, reduced repeats or score gains.')
    (ROOT/'evidence').mkdir(exist_ok=True)
    (ROOT/'evidence/replay-12.json').write_text(json.dumps(report,indent=2))
    return 0 if report['success'] else 1

if __name__=='__main__':sys.exit(main())
