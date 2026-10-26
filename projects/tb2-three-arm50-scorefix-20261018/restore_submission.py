"""Recover original file exclusively from observed reads and successful edits."""
import ast,hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parent
P=R.parent/'tb2-three-arm50-retry2-20261018/jobs/retry2-tb50-09-dsh-torch-pipeline-parallelism/torch-pipeline-parallelism__Ksib3ke/agent/live/dsh.jsonl'
rows=[json.loads(l) for l in P.read_text().splitlines()]
def result(call):return next(r for r in rows if r.get('type')=='tool_result' and r['callId']==call['callId'])
lines={};sources=[]
for i in (155,160,175):
 call=rows[i];res=result(call);assert res['status']=='completed'
 for n,text in re.findall(r'^(\d+): ?(.*)$',res['result'],re.M):
  n=int(n)
  if n in lines:assert lines[n]==text,('read disagreement',n)
  lines[n]=text
 sources.append(dict(row=i,call=call['callId']))
assert sorted(lines)==list(range(1,327)),('Missing lines',sorted(set(range(1,327))-lines.keys()))
content='\n'.join(lines[i] for i in range(1,327))+'\n'
for i,r in enumerate(rows):
 if i<180 or r.get('type')!='tool_call' or r.get('tool')!='edit':continue
 assert r['input']['file_path']=='/app/pipeline_parallel.py' and not r.get('truncated')
 res=result(r);assert res['status']=='completed'
 old,new=r['input']['old_string'],r['input']['new_string'];assert content.count(old)==1,(i,content.count(old))
 content=content.replace(old,new,1);sources.append(dict(row=i,call=r['callId']))
# Verify each surviving final read line, with no inferred or newly written code.
res=result(rows[228])
final_lines=content.splitlines()
for n,text in re.findall(r'^(\d+): ?(.*)$',res['result'],re.M):assert final_lines[int(n)-1]==text,('final read mismatch',n)
assert len(final_lines)==362
out=R/'recovered-submission';out.mkdir(exist_ok=True)
(out/'pipeline_parallel.py').write_text(content)
report=dict(original_trial=str(P.parents[2]),source_log_sha256=hashlib.sha256(P.read_bytes()).hexdigest(),file_sha256=hashlib.sha256(content.encode()).hexdigest(),lines=len(final_lines),sources=sources,model_calls=0,recovery='Complete reads at unchanged checkpoint, then exact successful edits; final read verified')
try:ast.parse(content);report['syntax_valid']=True
except SyntaxError as e:report['syntax_valid']=False;report['syntax_error']=str(e)
(out/'provenance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
