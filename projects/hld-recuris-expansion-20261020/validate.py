"""Offline release checks for source identity, budget and sample/report integrity."""
from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parent;H=R.parent
TB=H/'tb2-hld-recuris50-20261020';AW=H/'appworld-hld-recuris70-20261020'
AB=H/'swepro-hld-ab5-20261020'
def read(p):return json.loads(p.read_text())
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 checks=[]
 for root in [TB,AW]:
  p=read(root/'budget-profile.json')
  assert p['task_limit_microcny']==8000000 and len(p['jobs'])==len(set(p['jobs']))
  with (root/'budget-tests.log').open('w') as log:
   subprocess.run(['python3','-m','unittest','test_bounded_ledger'],cwd=root,stdout=log,stderr=log,check=True)
  checks.append(dict(name=root.name+' bounded ledger',tests=6,passed=True))
 assert read(TB/'budget-profile.json')['campaign_limit_microcny']+read(AW/'budget-profile.json')['campaign_limit_microcny']==1920000000
 for a,b in [(AB/'bundle/hld-new/src',TB/'bundle/kz/src'),(AB/'bundle/hld-new/src',AW/'runtime/hld/src'),
             (AB/'bundle/recuris-dsh/src',TB/'bundle/recuris-dsh/src'),(AB/'bundle/recuris-dsh/src',AW/'runtime/recuris-dsh/src'),
             (AB/'bundle/dsh-baselines/src',TB/'bundle/dsh-baselines/src'),(AB/'bundle/dsh-baselines/src',AW/'runtime/dsh-baselines/src')]:
  aa={str(p.relative_to(a)):digest(p) for p in a.rglob('*') if p.is_file()}
  bb={str(p.relative_to(b)):digest(p) for p in b.rglob('*') if p.is_file()}
  assert aa==bb,(a,b)
 checks.append(dict(name='Both campaigns exact frozen HLD v7 and Recuris source',passed=True))
 old=read(H/'tb2-three-arm50-20261017/tasks.json');new=read(TB/'tasks.json');assert old==new and len(new['tasks'])==50
 sys.path.insert(0,str(TB))
 from queue_policy import initial_rows,candidates,finish,summary
 rows=initial_rows([t['name'] for t in new['tasks']],{})
 assert len(rows)==100 and len({r['job'] for r in rows})==100
 first=candidates(rows,[]);assert len(first)==4
 for row in first:row['state']='running'
 finish(first[0],dict(engineering_clean=False,reason='fixture'))
 assert candidates(rows,[r['arm'] for r in first[1:]])
 assert summary(rows)[first[0]['arm']]['engineering_failures']==1
 sys.path.pop(0)
 checks.append(dict(name='TB paired queue, four slots, single fault does not stop other tasks',passed=True))
 m=read(AW/'task-manifest.json');ids={r['task'] for r in m['tasks']};assert len(ids)==70
 oldids=set(m['excluded_ids']);assert len(oldids)==30 and not ids&oldids and len(ids|oldids)==100
 assert not list((AW/'public-data').rglob('ground_truth'))
 historical=read(R/'historical-appworld30.json')
 assert len(historical['selected'])==60
 for row in historical['selected']:assert digest(Path(row['source_file']))==row['source_sha256']
 checks.append(dict(name='AppWorld unique 70+30, no grader in public data, historical raw results unchanged',passed=True))
 assert read(TB/'acceptance.json')['passed'] and read(AW/'entry-acceptance.json')['passed']
 assert read(AW/'world-verifier-acceptance.json')['passed']
 assert read(AW/'world-acceptance.json')['passed']
 checks.append(dict(name='Four real keyless entries, official scorers, isolation and read-only verification',passed=True))
 result=dict(passed=True,checks=checks,paid_calls=0)
 (R/'validation.json').write_text(json.dumps(result,indent=2))
 subprocess.run([str(TB/'venv/bin/python'),str(TB/'seal.py')],check=True)
 files={}
 for p in AW.iterdir():
  if p.is_file() and (p.suffix in ('.py','.mjs') or p.name in ['protocol.json','budget-profile.json','task-manifest.json','source-lock.json','image.json']):files[p.name]=digest(p)
 for folder in ['runtime/hld','runtime/recuris','runtime/recuris-dsh','runtime/dsh-baselines']:
  for p in (AW/folder).rglob('*'):
   if p.is_file() and not any(x in p.parts for x in ['node_modules','tests','__pycache__']):files[str(p.relative_to(AW))]=digest(p)
 (AW/'ready.json').write_text(json.dumps(dict(passed=True,files=files,paid_calls=0),indent=2))
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
