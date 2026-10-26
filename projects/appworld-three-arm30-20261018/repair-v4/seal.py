from pathlib import Path
import hashlib,json,sqlite3,time
from runner import R,V,read,save

assert not (V/'launch-once.marker').exists()
for name in ['offline-tests.json','world-verifier-acceptance.json','entry-acceptance.json']:
    assert read(V/name).get('passed'),name
for p in (R/'runtime/recuris-dsh').rglob('*'):
    if p.is_file() and not any(x in p.parts for x in ['node_modules','__pycache__']):
        assert p.read_bytes()==(V/'runtime/recuris-dsh'/p.relative_to(R/'runtime/recuris-dsh')).read_bytes()
rows={r['task']:r for r in read(R/'protocol.json')['tasks']}
original=[read(p) for p in (R/'jobs').glob('recuris*/summary.json')]
grouped={}
for s in original:grouped.setdefault(s['task'],[]).append(s)
queue=[];baseline=[]
for task,attempts in sorted(grouped.items()):
    passed=[s for s in attempts if s.get('official_success') is True]
    best=max(passed or attempts,key=lambda s:s.get('ended',0));baseline.append(best)
    assert best.get('grading')=='complete'
    if passed:continue
    row=dict(rows[task],_job='recuris--'+task+'--mechanism4',_attempt=best.get('attempt',1)+1,_rerun_of=best['job'])
    assert not (R/'jobs'/row['_job']).exists()
    queue.append({'arm':'recuris','row':row,'before_tests':[best['passed_tests'],best['total_tests']]})
assert len(grouped)==30 and len(queue)==3
save(V/'baseline.json',baseline)
save(V/'resume-plan.json',{'campaign_limit_cny':720,'attempt_limit_cny':8,'previous_completed':baseline,'queue':queue,'baseline_passed':{'recuris':27}})
preserved={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'jobs').glob('recuris*/*') if p.is_file() and p.name in ['summary.json','health.json','world-manifest.json']}
save(V/'original-result-manifest.json',preserved)
before=read(R/'budget-profile.json');save(V/'budget-profile-before.json',before)
profile=dict(before);profile['jobs']=list(before['jobs'])+[q['row']['_job'] for q in queue]
assert profile['campaign_limit_microcny']==720000000 and profile['task_limit_microcny']==8000000
with sqlite3.connect(R/'spending.sqlite',timeout=20) as db:
    with sqlite3.connect(V/'spending-before.sqlite') as backup:db.backup(backup)
    db.execute('BEGIN IMMEDIATE')
    old=json.loads(db.execute("SELECT value FROM meta WHERE key='profile'").fetchone()[0]);assert old==before
    db.execute("UPDATE meta SET value=? WHERE key='profile'",(json.dumps(profile,sort_keys=True),))
    save(R/'budget-profile.json',profile)
from spending import Ledger
ledger=Ledger(R/'spending.sqlite',profile);save(V/'budget-before.json',ledger.status())
files=[V/n for n in ['runner.py','world_server.py','appworld_guard.py','client.py','container-run.mjs','resume-plan.json','baseline.json','original-result-manifest.json']]
files += [R/n for n in ['spending.py','runtime_helper.py','repair_classification.py','grade.py','image.json','budget-profile.json']]
files += [p for p in (V/'runtime').rglob('*') if p.is_file() and not any(x in p.parts for x in ['node_modules','__pycache__','tests','.runtime'])]
save(V/'ready.json',{'passed':True,'sealed_at':time.time(),'tests':12,'entry_checks':1,'paid_calls_in_validation':0,'hashes':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})
print(json.dumps({'ready':True,'tasks':3,'max_new_cny':24,'budget_remaining_cny':ledger.status()['remaining_microcny']/1e6,'original_records':len(preserved)}))
