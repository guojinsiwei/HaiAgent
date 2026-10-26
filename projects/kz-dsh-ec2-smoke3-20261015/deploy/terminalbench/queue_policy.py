"""Pure two-pass policy. Score zero never triggers a retry."""
TERMINAL={'done','engineering_failure','historical'}

def initial_rows(names, history):
    rows=[]
    for i,task in enumerate(names):
        for arm in ('kz-dsh',):
            row=dict(task=task,arm=arm,stage='first',job=f'first-{i+1:02d}-{arm}-{task}',state='pending')
            old=None
            if old and old.get('attempted'):
                row.update(state='historical',result=old,engineering_clean=old['engineering_clean'])
            rows.append(row)
    return rows

def first_finished(rows):
    return all(r['state'] in TERMINAL for r in rows if r['stage']=='first')

def append_retry_batch(rows):
    if not first_finished(rows):return False
    if any(r['stage']=='retry' for r in rows):return False
    problems=[r for r in rows if not r.get('engineering_clean',False)]
    for r in problems:
        rows.append(dict(task=r['task'],arm=r['arm'],stage='retry',job=r['job'].replace('first-','retry-',1),
                         state='pending',retry_of=r['job']))
    return True

def candidates(rows, active_arms):
    stage='retry' if first_finished(rows) else 'first'
    return [r for r in rows if r['stage']==stage and r['state']=='pending' and r['arm'] not in active_arms]

def finish(row,result):
    row['result']=result
    row['engineering_clean']=bool(result.get('engineering_clean'))
    row['state']='done' if row['engineering_clean'] else 'engineering_failure'

def summary(rows):
    out={}
    for arm in ('kz-dsh',):
        first=[r for r in rows if r['arm']==arm and r['stage']=='first']
        retries=[r for r in rows if r['arm']==arm and r['stage']=='retry']
        latest={r['task']:r for r in first}
        latest.update({r['task']:r for r in retries if r['state'] in TERMINAL})
        out[arm]=dict(first_finished=sum(r['state'] in TERMINAL for r in first),total=len(first),
            retry_finished=sum(r['state'] in TERMINAL for r in retries),retry_total=len(retries),
            clean=sum(r.get('engineering_clean',False) for r in latest.values()),
            passed=sum(r.get('engineering_clean',False) and r.get('result',{}).get('reward')==1 for r in latest.values()))
    return out
