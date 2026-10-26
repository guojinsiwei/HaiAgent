"""Byte-budgeted prompt views; evidence originals stay in task-owned archives."""
from copy import deepcopy
import json

class ContextBudgetError(RuntimeError):
    """Controller input cannot fit; never a model protocol/recovery rejection."""

def message_bytes(messages):
    return len(json.dumps({'messages':messages},ensure_ascii=False).encode('utf-8'))

def excerpt(value,limit):
    data=value.encode('utf-8')
    if len(data)<=limit:return value
    marker='\n[partial context excerpt; original retained in task audit/history]\n'
    room=max(0,limit-len(marker.encode()))
    return data[:room//2].decode('utf-8','ignore')+marker+data[-(room-room//2):].decode('utf-8','ignore') if room else marker

def compact_data(value,limit=800):
    """Only observational views; never applied to task, memory or executable checks."""
    if isinstance(value,str):return excerpt(value,limit)
    if isinstance(value,list):
        rows=[compact_data(v,limit) for v in value[:8]]
        if len(value)>8:rows.append({'prompt_view_partial':True,'omitted_items':len(value)-8,
                                    'original_ref':'task audit/history'})
        return rows
    if isinstance(value,dict):
        result={k:compact_data(v,limit) for k,v in value.items()}
        if result!=value:result['prompt_view_partial']=True
        return result
    return value

def fit_payload(system,payload,budget,*,history_reserve=4000):
    """Allocate all roles' final system/current input together, preserving meanings.

    Mandatory task, whole memory views, subgoal definitions, IDs and budgets are
    retained. Only observational panels receive explicit partial views. No facts
    or conclusions are inferred. Full payload is logged by the calling controller.
    """
    p=deepcopy(payload);changes=[]
    def size():
        return message_bytes([{'role':'system','content':system},
            {'role':'user','content':json.dumps(p,ensure_ascii=False)}])
    original=size();target=budget-min(history_reserve,max(0,budget//8))
    fc=p.get('fixed_context',{})
    # A native receipt must not copy the same entire JSON observation again.
    receipt=fc.get('feedback',{}).get('tool_receipt') if isinstance(fc.get('feedback'),dict) else None
    if isinstance(receipt,dict) and 'result' in receipt:
        receipt.pop('result');receipt['result_ref']='same tool evidence and archived conversation observation'
        changes.append('duplicate_tool_receipt_result')
    if size()>target:
        while p.get('recent_decisions') and size()>target:
            p['recent_decisions'].pop(0)
            if 'recent_decisions' not in changes:changes.append('recent_decisions')
        while len(fc.get('evidence',[]))>1 and size()>target:
            fc['evidence'].pop(0)
            if 'old_evidence' not in changes:changes.append('old_evidence')
    for limit in (1600,800,400):
        if size()<=target:break
        for key in ('feedback','advice','semantic_review','contrastive_exploration','recovery',
                    'route_search','route_memory'):
            if key in fc:
                reduced=compact_data(fc[key],limit)
                if reduced!=fc[key]:fc[key]=reduced;changes.append(key+':'+str(limit))
        for row in fc.get('evidence',[]):
            for key in ('stdout','stderr','argv','purpose'):
                if isinstance(row.get(key),str):row[key]=excerpt(row[key],limit)
            row['prompt_view_partial']=True
        # Critic/monitor observations can grow independently of actor history.
        for key in ('actual_check_observations','observations','records','actor_summary','recent_decisions','handover_report'):
            if key in p:p[key]=compact_data(p[key],limit);changes.append(key+':'+str(limit))
    p['context_projection']={'original_bytes':original,'partial_fields':list(dict.fromkeys(changes)),
        'full_record_ref':'context_source event in task audit; recall_history for executed turns',
        'task_and_memories_complete':True,'budget_unit':'serialized UTF8 message bytes'}
    # Preserve the memory review's tail position after adding projection metadata.
    if 'fixed_context' in p:p['fixed_context']=p.pop('fixed_context')
    if size()>budget:
        raise ContextBudgetError('mandatory system/task/memory state cannot fit '+str(budget)+' UTF8 bytes')
    return p,{'input_bytes':size(),'original_bytes':original,'budget_bytes':budget,
              'partial_fields':list(dict.fromkeys(changes))}
