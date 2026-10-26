from collections import Counter
ARMS=('hld-old','hld-new')
TERMINAL={'done','engineering_failure','historical'}
def initial_rows(names,history):
 if len(names)!=10 or len(set(names))!=10:raise ValueError('Expected 10 unique frozen tasks')
 return [dict(task=t,arm=a,stage='first',job=f'tb2hld-{i+1:02d}-{a}-{t}',state='pending') for i,t in enumerate(names) for a in ARMS[i%2:]+ARMS[:i%2]]
def first_finished(rows):return all(r['state'] in TERMINAL for r in rows)
def append_retry_batch(rows):return False
def candidates(rows,active_arms):
 busy=Counter(active_arms);out=[]
 for r in rows:
  if sum(busy.values())>=4:break
  if r['state']=='pending' and busy[r['arm']]<2:out.append(r);busy[r['arm']]+=1
 return out
def finish(row,result):
 row.update(result=result,engineering_clean=bool(result.get('engineering_clean')),state='done' if result.get('engineering_clean') else 'engineering_failure')
def summary(rows):
 return {a:dict(total=len(rr),finished=sum(r['state'] in TERMINAL for r in rr),clean=sum(r.get('engineering_clean',False) for r in rr),
   scored=sum(type(r.get('result',{}).get('reward')) in (int,float) for r in rr),
   engineering_failures=sum(r['state']=='engineering_failure' for r in rr),
   passed=sum(r.get('engineering_clean',False) and r.get('result',{}).get('reward')==1 for r in rr)) for a in ARMS for rr in [[r for r in rows if r['arm']==a]]}
