"""Identical 50 tasks; rotate arm ordering and allow two concurrent jobs per arm."""
from collections import Counter
ARMS=('native-kz','kz-dsh','dsh')
TERMINAL={'done','engineering_failure','historical'}
def initial_rows(names,history):
    if len(names)!=50 or len(set(names))!=50:raise ValueError('Expected 50 unique tasks')
    rows=[]
    for i,t in enumerate(names):
        for a in ARMS[i%3:]+ARMS[:i%3]:
            rows.append(dict(task=t,arm=a,stage='first',job=f'tb50-{i+1:02d}-{a}-{t}',state='pending'))
    return rows
def first_finished(rows):return all(r['state'] in TERMINAL for r in rows)
def append_retry_batch(rows):return False
def candidates(rows,active_arms):
    busy=Counter(active_arms);selected=[]
    for r in rows:
        if sum(busy.values())>=6:break
        if r['state']=='pending' and busy[r['arm']]<2:
            selected.append(r);busy[r['arm']]+=1
    return selected
def finish(row,result):
    row['result']=result;row['engineering_clean']=bool(result.get('engineering_clean'))
    row['state']='done' if row['engineering_clean'] else 'engineering_failure'
def summary(rows):
    return {a:dict(total=len(rr),first_finished=sum(r['state'] in TERMINAL for r in rr),clean=sum(r.get('engineering_clean',False) for r in rr),passed=sum(r.get('engineering_clean',False) and r.get('result',{}).get('reward')==1 for r in rr)) for a in ARMS for rr in [[r for r in rows if r['arm']==a]]}
