import hashlib,json,shutil,tarfile,sqlite3
from pathlib import Path
from storage import atomic_json
from experiment import load,protocol_fields
ROOT=Path(__file__).resolve().parent
BASE=Path('/mnt/sdb/home/lizh639/tb2-native-kz-ten10-20261016')
NAMES=['polyglot-c-py','regex-log','sqlite-with-gcov']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not (ROOT/'dependencies').exists()
    state=json.loads((BASE/'admissions.json').read_text());assert state['state']=='finished' and not state['active']
    failures=[r for r in state['rows'] if r['state']=='engineering_failure']
    assert [r['task'] for r in failures]==NAMES
    seal=json.loads((BASE/'ready.json').read_text());assert seal['passed']
    for n,d in seal['files'].items():assert sha(BASE/n)==d,n
    shutil.copytree(BASE/'dependencies',ROOT/'dependencies');shutil.copytree(BASE/'environment-locks',ROOT/'environment-locks')
    for n in ('runtime-final.tar.gz','python-runtime.tar.gz','python-source.json'):shutil.copy2(BASE/n,ROOT/n)
    atomic_json(ROOT/'parent-results.json',state)
    tasks=json.loads((BASE/'tasks.json').read_text());tasks['tasks']=[t for t in tasks['tasks'] if t['name'] in NAMES]
    assert [t['name'] for t in tasks['tasks']]==NAMES
    tasks['selection']='User-authorized rerun of the three first-round native engineering failures'
    atomic_json(ROOT/'tasks.json',tasks);atomic_json(ROOT/'history.json',{})
    for n,d in json.loads((ROOT/'dependencies/ready.json').read_text())['files'].items():assert sha(ROOT/'dependencies'/n)==d
    with tarfile.open(ROOT/'native-runtime.tar.gz','w:gz') as a:
        for p in sorted((ROOT/'native').rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:a.add(p,arcname='kz-standalone/'+p.relative_to(ROOT/'native').as_posix())
    profile=json.loads((BASE/'budget-profile.json').read_text());profile['jobs']=[f'repair1-{i+1:02d}-native-kz-{n}' for i,n in enumerate(NAMES)]
    assert profile['campaign_limit_microcny']==40000000 and profile['task_limit_microcny']==4000000
    atomic_json(ROOT/'budget-profile.json',profile)
    source=sqlite3.connect('file:'+str(BASE/'spending.sqlite')+'?mode=ro',uri=True);target=sqlite3.connect(ROOT/'spending.sqlite')
    source.backup(target)
    assert target.execute("select count(*) from calls where state='reserved'").fetchone()[0]==0
    before=target.execute('select * from calls order by id').fetchall()
    target.execute("update meta set value=? where key='profile'",(json.dumps(profile,sort_keys=True),));target.commit()
    assert before==target.execute('select * from calls order by id').fetchall()
    imported=target.execute("select sum(case when state='settled' then actual else reserved end) from calls").fetchone()[0]
    source.close();target.close()
    atomic_json(ROOT/'budget-migration.json',dict(parent=str(BASE),imported_calls=len(before),imported_charged_microcny=imported,campaign_limit_microcny=40000000,original_unknown_reservations_retained=True))
    protocol=json.loads((BASE/'protocol.json').read_text());protocol.update(parent_runtime=str(BASE),paired_tasks=3,engineering_revision='native-transport-repair-2',
        arm_order='User-authorized three engineering retries, sequential',status='offline_acceptance_pending',
        comparison_limit='Explicit engineering rerun; original ten results and all prior costs retained separately',tasks_sha256=sha(ROOT/'tasks.json'),
        accounting_recovery='First unknown usage retains full reservation and permits bounded transport recovery; second unknown response stops that trial')
    protocol.update(protocol_fields(load(ROOT)));atomic_json(ROOT/'protocol.json',protocol)
    atomic_json(ROOT/'ready.json',dict(passed=False));print(json.dumps(dict(prepared=True,trials=3,imported_charged_microcny=imported,remaining_microcny=40000000-imported)))
if __name__=='__main__':main()
