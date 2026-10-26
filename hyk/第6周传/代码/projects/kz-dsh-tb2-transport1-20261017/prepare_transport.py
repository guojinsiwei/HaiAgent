"""Stage safely while the parent runs; inherit its final ledger before launch."""
import json,shutil,sqlite3,tarfile,hashlib,sys
from pathlib import Path
from storage import atomic_json
from queue_policy import initial_rows
from experiment import load,protocol_fields
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'tb2-kz-dsh-repair7-20261017'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_parent():
 for n,d in json.loads((BASE/'ready.json').read_text())['files'].items():assert sha(BASE/n)==d,n
def finalize():
 verify_parent()
 state=json.loads((BASE/'admissions.json').read_text());assert state['state']=='finished' and not state['active'],'Parent still active'
 selected=[r for r in state['rows'] if r['task']=='qemu-alpine-ssh' and r['arm']=='dsh'];assert len(selected)==1 and selected[0]['state']=='engineering_failure'
 assert not (ROOT/'spending.sqlite').exists()
 profile=json.loads((ROOT/'budget-profile.json').read_text())
 source=sqlite3.connect('file:'+str(BASE/'spending.sqlite')+'?mode=ro',uri=True);target=sqlite3.connect(ROOT/'spending.sqlite');source.backup(target)
 before=target.execute('select * from calls order by id').fetchall()
 target.execute("update meta set value=? where key='profile'",(json.dumps(profile,sort_keys=True),));target.commit()
 assert before==target.execute('select * from calls order by id').fetchall()
 imported=target.execute("select sum(case when state='settled' then actual else reserved end) from calls").fetchone()[0]
 source.close();target.close()
 atomic_json(ROOT/'parent-results.json',state)
 atomic_json(ROOT/'budget-migration.json',dict(parent=str(BASE),finalized=True,imported_calls=len(before),imported_charged_microcny=imported,campaign_limit_microcny=80000000,unknown_costs_retained=True))
 print(json.dumps(dict(finalized=True,charged_microcny=imported,remaining_microcny=80000000-imported)))
def prepare():
 verify_parent();assert not (ROOT/'runtime').exists()
 for n in ['dependencies','environment-locks']:shutil.copytree(BASE/n,ROOT/n,symlinks=True)
 for n in ['source.tar.gz','verifier-deps.tar.gz','verifier-deps-provenance.json']:shutil.copy2(BASE/n,ROOT/n)
 (ROOT/'runtime').mkdir()
 with tarfile.open(BASE/'runtime-final.tar.gz') as a:a.extractall(ROOT/'runtime',filter='data')
 shutil.copy2(ROOT/'provider-guard.mjs',ROOT/'runtime/kz/provider-guard.mjs')
 with tarfile.open(ROOT/'runtime-final.tar.gz','w:gz') as a:
  for p in sorted((ROOT/'runtime').iterdir()):a.add(p,arcname=p.name)
 tasks=json.loads((BASE/'tasks.json').read_text());tasks['tasks']=[t for t in tasks['tasks'] if t['name']=='qemu-alpine-ssh'];assert len(tasks['tasks'])==1
 tasks['selection']='User-authorized transport-failure rerun, pure DSH qemu-alpine-ssh only'
 atomic_json(ROOT/'tasks.json',tasks);atomic_json(ROOT/'history.json',{})
 rows=initial_rows(['qemu-alpine-ssh'],{});atomic_json(ROOT/'repair-queue.json',rows)
 profile=json.loads((BASE/'budget-profile.json').read_text());profile['jobs']=[r['job'] for r in rows]
 assert profile['campaign_limit_microcny']==80000000 and profile['task_limit_microcny']==4000000
 atomic_json(ROOT/'budget-profile.json',profile)
 atomic_json(ROOT/'parent-results.json',json.loads((BASE/'admissions.json').read_text()))
 atomic_json(ROOT/'budget-migration.json',dict(parent=str(BASE),finalized=False,policy='Wait for parent completion, preserve all charges; never fork a live budget'))
 protocol=json.loads((BASE/'protocol.json').read_text());protocol.update(parent_runtime=str(BASE),paired_tasks=1,engineering_revision='dsh-bounded-transport-recovery-3',tasks_sha256=sha(ROOT/'tasks.json'),bounded_design=profile,arm_order='Single pure DSH transport retry after parent completion',transport_repair='One transient transport retry per trial, full uncertain reservation retained; no TLS/auth retries')
 protocol.update(protocol_fields(load(ROOT)));atomic_json(ROOT/'protocol.json',protocol)
 atomic_json(ROOT/'ready.json',dict(passed=False));print('PREPARED; budget finalization pending')
if __name__=='__main__':finalize() if '--finalize' in sys.argv else prepare()
