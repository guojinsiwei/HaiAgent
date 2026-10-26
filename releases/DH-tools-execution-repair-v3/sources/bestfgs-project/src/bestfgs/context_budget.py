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

def data_bytes(value):
    return len(json.dumps(value,ensure_ascii=False).encode('utf-8'))

def bounded_observation(value,budget):
    """Bound arbitrary observational objects, including wide maps/long keys.

    Explicit source excerpt, never a fabricated JSON result or executable action.
    This fallback is not used on task, memory, subgoals, or the memory contract.
    """
    if data_bytes(value)<=budget:return value
    small=compact_data(value,200)
    if data_bytes(small)<=budget:return small
    marker={'prompt_view_partial':True,'original_bytes':data_bytes(value),
        'full_record_ref':'context_source audit; recall_history for executed observations'}
    if isinstance(value,dict):
        for key in ('id','evidence_id','return_code','timed_out','blocked','status','verdict','decision'):
            if key in value and data_bytes(value[key])<100:marker[key]=value[key]
    text=json.dumps(value,ensure_ascii=False)
    marker['source_excerpt']=''
    # Nested JSON escaping can enlarge a preview: measure the final object too.
    room=max(0,budget-data_bytes(marker)-80)
    marker['source_excerpt']=excerpt(text,room) if room>=120 else ''
    while data_bytes(marker)>budget and len(marker['source_excerpt'])>100:
        room//=2;marker['source_excerpt']=excerpt(text,room) if room>=120 else ''
    return marker

def evidence_view(row):
    """Keep real outcomes/IDs; don't repeat full dependency hash maps in prompts."""
    result=deepcopy(row)
    before=row.get('dependency_before');after=row.get('dependency_after')
    maps=('dependency_before','dependency_after','stable_dependencies','relevant_dependencies')
    removed=[key for key in maps if key in result]
    if not removed:return result
    for key in removed:result.pop(key,None)
    summary={'full_maps_ref':'original evidence '+str(row.get('id'))+' in conversation/audit',
        'removed_map_fields':removed,'changed_paths':[],'unknown_paths':[]}
    if isinstance(before,dict) and isinstance(after,dict):
        changed=[];unknown=[]
        for path in dict.fromkeys([*before,*after]):
            if path not in before or path not in after:unknown.append(path)
            elif before[path]!=after[path]:changed.append(path)
        summary.update(changed_paths=changed[:8],unknown_paths=unknown[:8],
            changed_path_count=len(changed),unknown_path_count=len(unknown),
            tracked_path_count=len(set(before)|set(after)))
    result.update(dependency_observation=summary,prompt_view_partial=True)
    return result

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
    feedback=fc.get('feedback')
    if isinstance(feedback,dict) and isinstance(feedback.get('evidence'),dict):
        row=feedback['evidence']
        if any(row==e for e in fc.get('evidence',[])):
            feedback.pop('evidence');feedback['evidence_id']=row.get('id')
            feedback['evidence_ref']='same record in fixed_context.evidence; original in conversation/audit'
            changes.append('duplicate_feedback_evidence')
    if size()>target:
        fc['evidence']=[evidence_view(row) for row in fc.get('evidence',[])]
        changes.append('evidence_dependency_maps')
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
    # Byte-bounded fallback applies to EVERY nonmandatory observational panel,
    # not a hard-coded subset. New metadata can no longer bypass the compressor.
    protected={'memories','subgoals','memory_action_contract','memory_budget',
               'current_workspace','budgets','memory_mode'}
    for cap in (1800,1000,600,350):
        if size()<=target:break
        for key,value in list(fc.items()):
            if key in protected or key=='evidence':continue
            reduced=bounded_observation(value,cap)
            if reduced!=value:fc[key]=reduced;changes.append(key+':byte_cap_'+str(cap))
        for row in fc.get('evidence',[]):
            for key in ('stdout','stderr','argv','purpose'):
                if isinstance(row.get(key),str):row[key]=excerpt(row[key],min(cap,600))
            for key,value in list(row.items()):
                if isinstance(value,(dict,list)):row[key]=bounded_observation(value,cap)
            row['prompt_view_partial']=True
        for key,value in list(p.items()):
            if key in ('task','fixed_context','context_projection'):continue
            reduced=bounded_observation(value,cap)
            if reduced!=value:p[key]=reduced;changes.append(key+':byte_cap_'+str(cap))
    p['context_projection']={'original_bytes':original,'partial_fields':list(dict.fromkeys(changes)),
        'full_record_ref':'context_source event in task audit; recall_history for executed turns',
        'task_and_memories_complete':True,'budget_unit':'serialized UTF8 message bytes'}
    # Preserve the memory review's tail position after adding projection metadata.
    if 'fixed_context' in p:p['fixed_context']=p.pop('fixed_context')
    if size()>budget:
        raise ContextBudgetError('mandatory system/task/memory state cannot fit '+str(budget)+' UTF8 bytes')
    return p,{'input_bytes':size(),'original_bytes':original,'budget_bytes':budget,
              'partial_fields':list(dict.fromkeys(changes))}
