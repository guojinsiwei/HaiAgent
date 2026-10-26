"""Seal acceptance, immutable baseline and append-only retry authorization."""
from pathlib import Path
import json,hashlib,sqlite3,time,sys,subprocess
V=Path(__file__).resolve().parent;R=V.parent
sys.path.insert(0,str(R))
from spending import Ledger

def read(p):return json.loads(p.read_text())
def save(p,data):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

assert not (V/'ready.json').exists(),'Already sealed; validate existing deployment instead of replacing it'
for name in ['offline-tests.json','world-acceptance.json','entry-acceptance.json','historical-replay.json']:
    assert read(V/name)['passed'],name
assert not subprocess.check_output(['docker','ps','--filter','label=experiment='+R.name,'--format','{{.Names}}'],text=True).strip(),'Existing campaign containers must finish first'
baseline=read(R/'audit/method-analysis-20261019/task-comparison.json')
manifest=read(R/'protocol.json');tasks={x['task']:x for x in manifest['tasks']}
queue=[]
for row in baseline:
    for arm in ['hld','kzdsh-new']:
        old=row['arms'][arm]
        if old['pass']:continue
        fresh=dict(tasks[row['task']]);fresh.update(_job=arm+'--'+row['task']+'--mechanism2',_attempt=3 if '--repair1' in old['job'] else 2,_rerun_of=old['job'])
        assert not (R/'jobs'/fresh['_job']).exists()
        queue.append({'arm':arm,'row':fresh,'before_tests':old['tests'],'reason':'mechanism-v2 repair audit: public scope, verification identity/protocol, and AppWorld adapter'})
assert len(queue)==15
priority=['hld--13547f5_2','hld--13547f5_3','kzdsh-new--0d01c76_1','hld--90adc3f_3','kzdsh-new--2c544f9_1','hld--2c544f9_1']
queue.sort(key=lambda x:priority.index(x['arm']+'--'+x['row']['task']) if x['arm']+'--'+x['row']['task'] in priority else len(priority))
profile=read(R/'budget-profile.json');ledger=Ledger(R/'spending.sqlite',profile);before=ledger.status()
assert before['reserved_microcny']==0 and before['halt_reason'] is None
assert before['remaining_microcny']>=len(queue)*profile['task_limit_microcny']
assert profile['campaign_limit_microcny']==720000000 and profile['task_limit_microcny']==8000000

original={}
for p in (R/'jobs').glob('*/*'):
    if p.name in ['summary.json','health.json','world-manifest.json'] and p.is_file():original[str(p.relative_to(R))]=sha(p)
for p in (R/'jobs').glob('*/grade/result.json'):original[str(p.relative_to(R))]=sha(p)
save(V/'original-result-manifest.json',original);save(V/'baseline.json',baseline)
save(V/'budget-before.json',before);save(V/'original-budget-profile.json',profile)
with sqlite3.connect(R/'spending.sqlite') as source,sqlite3.connect(V/'spending-before.sqlite') as target:source.backup(target)
plan={'campaign_limit_cny':720,'attempt_limit_cny':8,'max_new_cny':120,'queue':queue,'previous_completed':[],
      'retry_count':15,'workers':6,'baseline_passed':{'hld':19,'kzdsh-new':26,'recuris':27,'dsh':25},'paid_calls_before':before}
save(V/'resume-plan.json',plan)
new={**profile,'jobs':profile['jobs']+[x['row']['_job'] for x in queue]}
assert len(set(new['jobs']))==len(new['jobs'])
with sqlite3.connect(R/'spending.sqlite',timeout=20) as db:
    db.execute('BEGIN IMMEDIATE')
    assert json.loads(db.execute("select value from meta where key='profile'").fetchone()[0])==profile
    db.execute("update meta set value=? where key='profile'",(json.dumps(new,sort_keys=True),))
save(R/'budget-profile.json',new)
assert Ledger(R/'spending.sqlite',new).status()==before,'Profile extension changed spending'
files=[V/n for n in ['runner.py','world_server.py','client.py','appworld_guard.py','container-run.mjs','resume-plan.json','baseline.json','original-result-manifest.json']]
files += [R/n for n in ['spending.py','runtime_helper.py','repair_classification.py','grade.py','budget-profile.json','image.json']]
for arm in ['hld','kzdsh-new']:
    d=V/'runtime'/arm
    files += list((d/'src').glob('*.mjs'))+list(d.glob('*.mjs'))+list((d/'config').glob('*.yml'))+list((d/'.runtime').glob('*.yml'))+[d/'route.patch.yml']
save(V/'ready.json',{'passed':True,'sealed_at':time.time(),'paid_calls_in_validation':0,'tests':243,'hashes':{str(p.relative_to(R)):sha(p) for p in files},'budget_before':before,'retry_count':15})
print(json.dumps({'sealed':True,'attempts':15,'max_new_cny':120,'remaining_cny':before['remaining_microcny']/1e6,'workers':6,'original_result_files':len(original)}))
