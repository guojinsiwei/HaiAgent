"""Create isolated continuations from preserved workspaces and sessions."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time
R=Path(__file__).resolve().parent;B=R.parent;P=B/'longcli-hld-full20-triple-20261022';OUT=R/'longcli-v2'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,indent=2))
def once(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def replace_file(p,text):
    if p.exists():p.unlink() # break hardlinks before changing a recovery copy
    p.write_text(text)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=False)
    rows=[];base=read(P/'protocol.json')
    sources=[R/'longcli']
    for source in sources:
        for d in sorted((source/'jobs').iterdir()):
            old=read(d/'summary.json')
            if not old.get('engineering_fault'):continue
            row=dict(next(x for x in base['tasks'] if x['task']==old['task']))
            live=d/'logs/live';sessions=list((live/'dsh-home/sessions').glob('*/session-*/session.v4.jsonl.zstd'))
            row.update(budget_job=old['job'],recovery_source=str(d),previous_requests=old['requests'],
                       remaining_seconds=max(1,next(x['remaining_seconds'] for x in read(source/'protocol.json')['tasks'] if x['budget_job']==old['job'])-int(old['ended']-old['started'])),
                       resume_session=sessions[0].parent.name if len(sessions)==1 and old['tools']>0 else None)
            assert len(sessions)<=1
            rows.append(row)
    assert len(rows)==6
    for n in ['common.py','spending.py','college_grader.py']:
        shutil.copy2(B/'longcli-hld-resource-match-20261022'/n,OUT/n)
    for n in ['circuit.py','model_proxy.py']:(OUT/n).symlink_to(R/n)
    (OUT/'upstream').symlink_to(P/'upstream',target_is_directory=True)
    (OUT/'empty-tests').mkdir();(OUT/'runtime').mkdir()
    (OUT/'runtime/node').symlink_to(P/'runtime/node',target_is_directory=True)
    shutil.copytree(P/'runtime/kz',OUT/'runtime/kz',copy_function=os.link,symlinks=True)
    target=OUT/'runtime/kz/provider-guard.mjs';replace_file(target,(R/'provider-guard.mjs').read_text())
    shared=(B/'lhtb-hld-v8-recuris24-20261022/bundle/kz/shared-budget.mjs').read_text()
    replace_file(OUT/'runtime/kz/shared-budget-high.mjs',shared)
    entry=(B/'longcli-hld-resource-match-20261022/entry-run.mjs').read_text()
    entry=once(entry,"{flag:'wx'}","{flag:'w'}")
    entry=once(entry,"args.push('--json','-');","if(bundle.resume_session)args.push('--session-id',bundle.resume_session);\nargs.push('--json','-');")
    entry=once(entry,'child.stdin.end(bundle.instruction)',"child.stdin.end(bundle.resume_session?'Continue the original task from the preserved workspace and session. The model connection was interrupted and has now recovered.':bundle.instruction)")
    entry=once(entry,'deadline(child,7200,','deadline(child,bundle.remaining_seconds,')
    (OUT/'entry-run.mjs').write_text(entry)
    runner=(B/'longcli-hld-resource-match-20261022/runner.py').read_text()
    runner=once(runner,"job='hld-resource-match--'+row['task']","job=row['budget_job']")
    runner=once(runner,"import_tree(row['starter_path'],directory/'workspace')","shutil.copytree(Path(row['recovery_source'])/'workspace',directory/'workspace',symlinks=True)")
    runner=once(runner,"for part in ['home','logs']:(directory/part).mkdir()", """for part in ['home','logs']:(directory/part).mkdir()
 oldlive=Path(row['recovery_source'])/'logs/live';newlive=directory/'logs/live';newlive.mkdir()
 if row.get('resume_session'):
  for part in ['dsh-home','kz']:
   if (oldlive/part).exists():shutil.copytree(oldlive/part,newlive/part,symlinks=True)
 for statefile in (newlive/'kz').glob('*.json'):
   state=read(statefile,{})
   if isinstance(state.get('full'),dict) and 'startedAt' in state['full']:
    state['full']['startedAt']=int(time.time()*1000)-(7200-row['remaining_seconds'])*1000
    save(statefile,state)
 oldstate=read(oldlive/'shared-state.json',{})
 oldstate['stopped']=None
 save(newlive/'shared-state.json',oldstate)
 save(directory/'recovery.json',dict(source=row['recovery_source'],session=row.get('resume_session'),same_budget_job=row['budget_job'],previous_requests=row['previous_requests'],remaining_seconds=row['remaining_seconds']))""")
    runner=once(runner,"attempt_id=job,spending=dict(","attempt_id=job,resume_session=row.get('resume_session'),remaining_seconds=row['remaining_seconds'],spending=dict(")
    runner=once(runner,'if time.time()-start>(120 if probe else 7260):','if time.time()-start>(120 if probe else row[\'remaining_seconds\']+60):')
    runner=once(runner,'if not probe:proxy=Proxy(gateway)',"if not probe:\n   from recovery_proxy import RecoveryProxy\n   proxy=RecoveryProxy(gateway)")
    (OUT/'runner.py').write_text(runner)
    (OUT/'recovery_proxy.py').write_text("""from pathlib import Path
from circuit import Circuit
from model_proxy import server
ROOT=Path(__file__).resolve().parent.parent
class RecoveryProxy:
 def __init__(self,gateway):
  self.server=server(gateway,Circuit(ROOT/'provider-circuit.sqlite'),ROOT/'longcli-proxy.jsonl')
  self.url=f'http://{gateway}:{self.server.server_port}'
 def close(self):self.server.shutdown();self.server.server_close()
""")
    protocol={**base,'experiment':'longcli-transport-recovery-20261023','tasks':rows,'methods':['hld-resource-match','hld-request400'],
              'total_trials':6,'concurrency':3,'requests_per_task':800,'max_output_tokens':32768,
              'shared_ledger':str(P/'spending.sqlite'),'recovery_uses_original_job_caps':True,'historical_results_preserved':True}
    save(OUT/'protocol.json',protocol)
    shutil.copy2(P/'input-manifest.json',OUT/'input-manifest.json')
    for row in rows:
        assert sha(Path(row['starter_path']))==row['starter_sha256']
        subprocess.run(['docker','image','inspect',row['image_id']],stdout=subprocess.DEVNULL,check=True)
    for f in OUT.glob('*.py'):compile(f.read_text(),str(f),'exec')
    subprocess.run([str(OUT/'runtime/node/bin/node'),'--check',str(OUT/'entry-run.mjs')],check=True)
    # No solver source changes: both implementations remain frozen.
    for f in (P/'runtime/kz/src').rglob('*'):
        if f.is_file():assert sha(f)==sha(OUT/'runtime/kz/src'/f.relative_to(P/'runtime/kz/src'))
    save(OUT/'preflight.json',dict(passed=True,model_calls=0,tasks=[r['task'] for r in rows],
         source_unchanged=True,shared_original_ledger=True,created=time.time()))
    print(json.dumps(dict(prepared=True,tasks=[r['task'] for r in rows],resumed_sessions=sum(bool(r['resume_session']) for r in rows))))
if __name__=='__main__':main()
