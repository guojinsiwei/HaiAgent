"""Task-local exploration observations; no model requests or causal oracle."""
import re,json

DIMENSIONS=('dependency_dimension','target_dimension','command_dimension')
def terms(value):return set(re.findall(r'[\w.-]+',str(value or '').lower()))
def nonempty(value):return isinstance(value,str) and value.strip() and '\0' not in value

def validate_comparison(proof,changed):
    if not isinstance(proof,dict) or any(not nonempty(proof.get(k)) for k in DIMENSIONS):
        raise ValueError('Active exploration requires all three comparison fields; state what stays unchanged.')
    if not isinstance(changed,list) or not changed or any(k not in DIMENSIONS for k in changed):
        raise ValueError('Active exploration requires changed_dimensions naming at least one relevant dimension.')

def validate_experiment(value):
    if not isinstance(value,dict) or not nonempty(value.get('hypothesis')):
        raise ValueError('Active exploration requires an exploration hypothesis and supports/refutes observations.')
    for key in ('supports','refutes'):
        p=value.get(key)
        if not isinstance(p,dict) or p.get('field') not in ('stdout','stderr') or not nonempty(p.get('contains')) or len(p['contains'])>240:
            raise ValueError('Exploration predictions need field stdout|stderr and a nonempty contains literal (max 240).')
    a,b=value['supports'],value['refutes']
    if a['field']==b['field'] and (a['contains'] in b['contains'] or b['contains'] in a['contains']):
        raise ValueError('Exploration predictions must distinguish support from refutation.')
    return dict(hypothesis=value['hypothesis'],supports=dict(field=a['field'],contains=a['contains']),refutes=dict(field=b['field'],contains=b['contains']))

def select_anchors(rows,trigger_key=None,query='',targets=(),goal=None,limit=3):
    groups={};q=terms(query);wanted=set(targets)
    for row in rows:
        key=row.get('check_key',row.get('command_key'));prev=groups.get(key,{})
        groups[key]=dict(row,attempts=prev.get('attempts',0)+1,
            evidence_ids=(prev.get('evidence_ids',[])+[row['evidence_id']])[-4:],
            conditions_changed=bool(prev) and (prev.get('scope')!=row.get('scope') or prev.get('conditions_changed',False)))
    scored=[]
    for i,row in enumerate(groups.values()):
        score=(1000 if trigger_key and row.get('check_key')==trigger_key else 0)+(30 if goal and row.get('goal')==goal else 0)
        score+=8*len(wanted & set(row.get('dependencies',{})))+len(q & terms(row['command']+' '+row['observation']))
        if score or not (query or targets or goal or trigger_key):scored.append((score,i,row))
    return [r for _,_,r in sorted(scored,key=lambda x:(x[0],x[1]),reverse=True)[:limit]]

def result_memory(plan,row,assessment,local_defect=False):
    usable=not any(row.get(k,False) for k in ('capture_incomplete','terminal_projection_incomplete','timed_out','blocked')) and not local_defect
    usable=usable and isinstance(row.get('return_code'),int) and not (row['return_code']==0 and not assessment['execution_clean'])
    exp=plan['experiment']
    matches=lambda k:usable and exp[k]['contains'] in row.get(exp[k]['field'],'')
    support,refute=matches('supports'),matches('refutes')
    status=('supported' if support else 'refuted') if support!=refute else 'unknown'
    reason='execution_unusable' if not usable else 'conflicting_observations' if support and refute else 'no_predicted_observation' if not support and not refute else 'exclusive_predicted_observation'
    return dict(id='X'+row['id'],evidence_id=row['id'],episode=plan['episode'],anchor_ids=plan['anchor_ids'],
        check_key=plan.get('check_key'),goal=plan.get('goal'),kind=plan['kind'],command=plan['command'],
        hypothesis=exp['hypothesis'],predictions=dict(supports=exp['supports'],refutes=exp['refutes']),status=status,reason=reason,
        evidence=[dict(field=exp[k]['field'],quote=exp[k]['contains']) for k in ('supports','refutes') if matches(k)],
        conditions=dict(before=row['before'],after=row['after'],dependencies=row.get('dependency_after',{})),
        semantic_verified=False,task_success=None,next_use={
            'refuted':'Reconsider this hypothesis under the recorded conditions; cite new evidence before retrying it.',
            'supported':'Use this observation to choose a repair or verification; the causal explanation remains a hypothesis.',
            'unknown':'This attempt did not distinguish the hypothesis; inspect the failure or choose a different observation.'}[status])

def recall_results(rows,query='',check_key=None,goal=None,scope=None,dependencies=None,limit=3):
    q=terms(query);scored=[];dependencies=dependencies or {}
    for i,row in enumerate(rows):
        score=(1000 if check_key and row.get('check_key')==check_key else 0)+(30 if goal and row.get('goal')==goal else 0)+len(q & terms(row['hypothesis']+' '+row['command']))
        if score or not (query or check_key or goal):scored.append((score,i,row))
    result=[]
    for _,_,row in sorted(scored,key=lambda x:(x[0],x[1]),reverse=True)[:limit]:
        applicability=('same_recorded_workspace_external_state_unverified' if row['conditions']['after']==scope else
            'dependencies_changed_recheck' if any(k in dependencies and dependencies[k]!=v for k,v in row['conditions']['dependencies'].items()) else 'historical_conditions_recheck')
        result.append(dict(row,applicability=applicability))
    return result

def result_views(rows,budget=2600):
    views=[dict(id=r['id'],evidence_id=r['evidence_id'],anchor_ids=r['anchor_ids'][-4:],hypothesis=r['hypothesis'][:350],
        status=r['status'],reason=r['reason'],evidence=r['evidence'],applicability=r['applicability'],
        conditions=dict(before=r['conditions']['before'],after=r['conditions']['after']),next_use=r['next_use'],
        semantic_verified=False,task_success=None) for r in rows]
    while len(views)>1 and len(json.dumps(views,ensure_ascii=False))>budget:views.pop()
    return views
