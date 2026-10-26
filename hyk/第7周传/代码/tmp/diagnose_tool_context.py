"""Read failing public audit on its host; report only sizes and paths."""
import json,sys
from pathlib import Path
ROOT=Path('/var/tmp/longcli-dh-tools-context-repair-20261008')
sys.path[:0]=[str(ROOT/'sources/bestfgs-project/src')]
from bestfgs.context_budget import fit_payload,message_bytes,compact_data,excerpt
path=ROOT/'jobs/dh_tools--cmu15_445_p2/trace/events.jsonl'
systems={};last=None;failure=None
for line in path.open():
    e=json.loads(line)
    if e.get('event')=='final_prompt':systems[e['role']]=e['messages'][0]['content']
    if e.get('event')=='context_source':last=e
    if e.get('event')=='context_budget_failure':failure=e
assert last
p=last['payload'];s=systems[last['role']]
def size(v):return len(json.dumps(v,ensure_ascii=False).encode('utf-8'))
rows=[]
def visit(v,path):
    rows.append({'path':path,'bytes':size(v),'type':type(v).__name__})
    if isinstance(v,dict):
        for k,x in v.items():visit(x,path+'.'+k)
    elif isinstance(v,list):
        for i,x in enumerate(v):visit(x,path+'['+str(i)+']')
visit(p,'payload')
out={'role':last['role'],'source_seq':last.get('seq',last.get('sequence')),'system_bytes':len(s.encode()),
    'complete_bytes':message_bytes([{'role':'system','content':s},
        {'role':'user','content':json.dumps(p,ensure_ascii=False)}]),
    'largest_fields':sorted(rows,key=lambda r:r['bytes'],reverse=True)[:30]}
try:fit_payload(s,p,44976);out['reproduced']=False
except Exception as e:
    out['reproduced']=True;out['error_type']=type(e).__name__
    tb=e.__traceback__
    while tb:
        if tb.tb_frame.f_code.co_name=='fit_payload':
            v=tb.tb_frame.f_locals['p'];rows=[];visit(v,'projected')
            out['after_compression_bytes']=message_bytes([{'role':'system','content':s},
                {'role':'user','content':json.dumps(v,ensure_ascii=False)}])
            out['largest_remaining_fields']=sorted(rows,key=lambda r:r['bytes'],reverse=True)[:22]
        tb=tb.tb_next
print(json.dumps(out))
# Audit was already credential-redacted by Recorder; this fixture stays task-owned.
dest=ROOT/'evidence/current-failure-context.json'
dest.write_text(json.dumps({'system':s,'payload':p},ensure_ascii=False),encoding='utf-8')
