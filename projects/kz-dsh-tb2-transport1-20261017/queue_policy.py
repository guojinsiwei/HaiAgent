"""Frozen paired queue; alternate arm order and never retry automatically."""
TERMINAL={'done','engineering_failure','historical'}

AUTHORIZED=[('qemu-alpine-ssh','dsh')]

def initial_rows(names, history):
    if set(names)!={t for t,a in AUTHORIZED}:raise ValueError('Unexpected repair selection')
    return [dict(task=t,arm=a,stage='first',job=f'repair2-{i+1:02d}-{a}-{t}',state='pending') for i,(t,a) in enumerate(AUTHORIZED)]

def first_finished(rows):
    return all(r['state'] in TERMINAL for r in rows if r['stage']=='first')

def append_retry_batch(rows):
    return False

def candidates(rows, active_arms):
    selected=[];busy=set(active_arms)
    for row in rows:
        if len(busy)>=1:break
        if row['state']=='pending' and row['arm'] not in busy:
            selected.append(row);busy.add(row['arm'])
    return selected

def finish(row,result):
    row['result']=result
    row['engineering_clean']=bool(result.get('engineering_clean'))
    row['state']='done' if row['engineering_clean'] else 'engineering_failure'

def summary(rows):
    out={}
    for arm in ('dsh','kz-dsh'):
        first=[r for r in rows if r['arm']==arm and r['stage']=='first']
        retries=[r for r in rows if r['arm']==arm and r['stage']=='retry']
        latest={r['task']:r for r in first}
        latest.update({r['task']:r for r in retries if r['state'] in TERMINAL})
        out[arm]=dict(first_finished=sum(r['state'] in TERMINAL for r in first),total=len(first),
            retry_finished=sum(r['state'] in TERMINAL for r in retries),retry_total=len(retries),
            clean=sum(r.get('engineering_clean',False) for r in latest.values()),
            passed=sum(r.get('engineering_clean',False) and r.get('result',{}).get('reward')==1 for r in latest.values()))
    return out
