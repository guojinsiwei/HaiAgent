from repair_classification import classify,retry_eligible

def make_plan(protocol,summaries):
    rows={r['task']:r for r in protocol['tasks']};done={(s['arm'],s['task']) for s in summaries}
    retry=[];pending=[]
    for s in summaries:
        if retry_eligible(s):
            row=dict(rows[s['task']],_job=s['job']+'--repair1',_attempt=2,_rerun_of=s['job'])
            retry.append({'arm':s['arm'],'row':row,'cause':s['repair_cause']})
    arms=protocol['methods']
    for i,row in enumerate(protocol['tasks']):
        for arm in arms[i%4:]+arms[:i%4]:
            if (arm,row['task']) not in done:pending.append({'arm':arm,'row':row})
    return {'campaign_limit_cny':720,'attempt_limit_cny':8,'previous_completed':summaries,
            'retry_count':len(retry),'unstarted_count':len(pending),'queue':retry+pending}
