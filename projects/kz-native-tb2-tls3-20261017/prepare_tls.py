"""Prepare a new immutable deployment, retaining every historical charge."""
import json,shutil,sqlite3,tarfile,hashlib
from pathlib import Path
from storage import atomic_json
from experiment import load,protocol_fields
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'tb2-native-kz-repair3-20261016'
PAIRED=ROOT.parent/'tb2-kz-dsh-repair7-20261017'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not (ROOT/'spending.sqlite').exists()
 state=json.loads((BASE/'admissions.json').read_text());assert state['state']=='finished' and not state['active']
 assert {r['task'] for r in state['rows'] if r['state']=='engineering_failure'}=={'polyglot-c-py','regex-log','sqlite-with-gcov'}
 for n,d in json.loads((BASE/'ready.json').read_text())['files'].items():assert sha(BASE/n)==d,n
 for n in ['dependencies','environment-locks']:shutil.copytree(BASE/n,ROOT/n,symlinks=True)
 for n in ['runtime-final.tar.gz','python-runtime.tar.gz','python-source.json','historical-regression.json','tasks.json']:shutil.copy2(BASE/n,ROOT/n)
 for n in ['verifier-deps.tar.gz','verifier-deps-provenance.json']:shutil.copy2(PAIRED/n,ROOT/n)
 ca=PAIRED/'venv/lib/python3.12/site-packages/certifi/cacert.pem';shutil.copy2(ca,ROOT/'native/cacert.pem')
 atomic_json(ROOT/'ca-provenance.json',dict(source=str(ca),sha256=sha(ca),bundle='Installed certifi Mozilla CA bundle',tls_verification=True))
 with tarfile.open(ROOT/'native-runtime.tar.gz','w:gz') as a:
  for p in sorted((ROOT/'native').rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts:a.add(p,arcname='kz-standalone/'+p.relative_to(ROOT/'native').as_posix())
 atomic_json(ROOT/'parent-results.json',state);atomic_json(ROOT/'history.json',{})
 profile=json.loads((BASE/'budget-profile.json').read_text());profile['jobs']=[f'repair2-{i+1:02d}-native-kz-{t}' for i,t in enumerate(['polyglot-c-py','regex-log','sqlite-with-gcov'])]
 assert profile['campaign_limit_microcny']==40000000 and profile['task_limit_microcny']==4000000
 atomic_json(ROOT/'budget-profile.json',profile)
 source=sqlite3.connect('file:'+str(BASE/'spending.sqlite')+'?mode=ro',uri=True);target=sqlite3.connect(ROOT/'spending.sqlite');source.backup(target)
 before=target.execute('select * from calls order by id').fetchall()
 target.execute("update meta set value=? where key='profile'",(json.dumps(profile,sort_keys=True),));target.commit()
 assert before==target.execute('select * from calls order by id').fetchall()
 imported=target.execute('select sum(case when state=\'settled\' then actual else reserved end) from calls').fetchone()[0]
 source.close();target.close()
 atomic_json(ROOT/'budget-migration.json',dict(parent=str(BASE),finalized=True,imported_calls=len(before),imported_charged_microcny=imported,campaign_limit_microcny=40000000,unknown_costs_retained=True))
 protocol=json.loads((BASE/'protocol.json').read_text());protocol.update(parent_runtime=str(BASE),engineering_revision='native-verified-ca-3',tasks_sha256=sha(ROOT/'tasks.json'),tls_repair='Explicit trusted CA bundle plus keyless pre-admission TLS check; verification remains required')
 protocol.update(protocol_fields(load(ROOT)));atomic_json(ROOT/'protocol.json',protocol)
 atomic_json(ROOT/'ready.json',dict(passed=False));print(json.dumps(dict(prepared=True,charged_microcny=imported,remaining_microcny=40000000-imported)))
if __name__=='__main__':main()
