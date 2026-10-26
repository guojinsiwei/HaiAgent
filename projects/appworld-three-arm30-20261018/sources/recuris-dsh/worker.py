"""Frozen historical Recuris E/W/rho/C; DSH owns all execution."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
from recuris import working, memory, prompts
from recuris.protocol import parse_object, ProtocolError

def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)

def ask(role, system, payload, validate):
    repair=None
    # Historical protocol-repair4: recovery uses the common request budget,
    # not a second arbitrary rejection/length cap.
    while True:
        emit({'type':'llm','role':role,'system':system,'payload':{'original_task':instruction,**payload,'format_repair':repair}})
        reply=json.loads(sys.stdin.readline())
        if reply.get('error'): raise RuntimeError(reply['error'])
        try: return validate(parse_object(reply['text']))
        except (ProtocolError, ValueError, TypeError, KeyError) as exc:
            repair={'error':str(exc),'previous_response':reply['text']}
            emit({'type':'event','event':'protocol_repair','detail':{'role':role,'error':str(exc)}})

M=memory.load_memory(Path(__file__).parent/'vendor/terminal_seed.json')
state=[]; receipts={}; revision=0; step=0; previous=None; skills=[]; instruction=''

def panel():
    return {'variant':'Recuris historical frozen on DSH','original_task':instruction,
            'working_memory':state,'delivered_skills':skills,'revision':revision,
            'receipt_ids':list(receipts),'memory_sha256':memory.memory_digest(M)}

def dispatch(q):
    global state, revision, step, previous, skills, instruction
    op=q['op']
    if op=='init':
        instruction=q['instruction']
        # Original role and immutable requirement; no truncated alternate task.
        state=ask('recuris_initialize',prompts.INITIALIZE,
            {'W':M['W'],'environment':q['environment']},lambda value:working.initialize(value,M['W']['max_goals']))
    elif op=='observe':
        row=q['receipt']; receipts[row['id']]=row
        if q.get('mutation'):
            revision+=1; state=working.invalidate_completions(state)
        row['revision']=revision
        state,decisions=ask('recuris_update',prompts.UPDATE,
            {'working_memory':state,'action':q['action'],'observation':row,'W':M['W'],'C':M['C']},
            lambda value:working.apply_proposal(state,value,receipts,revision,M))
        emit({'type':'event','event':'working_commit','detail':{'decisions':decisions,'receipt':row}})
    elif op=='verification':
        goal=next(g for g in state if g['id']==q['goal_id'])
        return {'goal':goal,'digest':working.verifier_digest(goal['verification']),'revision':revision}
    elif op=='step':
        step+=1
        delivered=memory.invoke(M,state,step,previous)
        previous=memory.unresolved_signature(state)
        if delivered: skills=delivered
    elif op=='complete':
        return {'accepted':bool(state) and all(g['status']=='done' for g in state),'state':panel()}
    elif op!='snapshot': raise ValueError('unknown operation')
    return panel()

for line in sys.stdin:
    try: emit({'type':'result','value':dispatch(json.loads(line))})
    except Exception as exc:
        emit({'type':'event','event':'engineering_error','detail':{'message':str(exc),'kind':type(exc).__name__}})
        emit({'type':'result','error':f'{type(exc).__name__}: {exc}'})
