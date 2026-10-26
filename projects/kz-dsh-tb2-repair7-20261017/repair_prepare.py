import hashlib,json,shutil,sqlite3,tarfile
from pathlib import Path
from storage import atomic_json
from experiment import load,protocol_fields
from queue_policy import AUTHORIZED,initial_rows
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'tb2-kz-dsh-paired10-20261016'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not (ROOT/'spending.sqlite').exists()
 state=json.loads((BASE/'admissions.json').read_text());assert state['state']=='finished' and not state['active']
 failures=[(r['task'],r['arm']) for r in state['rows'] if r['state']=='engineering_failure']
 assert len(failures)==len(AUTHORIZED) and set(failures)==set(AUTHORIZED)
 for n,d in json.loads((BASE/'ready.json').read_text())['files'].items():assert sha(BASE/n)==d,n
 for n in ['dependencies','environment-locks']:
  if not (ROOT/n).exists():shutil.copytree(BASE/n,ROOT/n,symlinks=True)
 # Expand the sealed clean runtime, never old mutable test scratch directories.
 assert not (ROOT/'runtime').exists()
 (ROOT/'runtime').mkdir()
 with tarfile.open(BASE/'runtime-final.tar.gz') as archive:archive.extractall(ROOT/'runtime',filter='data')
 for n in ['runtime-final.tar.gz','source.tar.gz']:shutil.copy2(BASE/n,ROOT/n)
 atomic_json(ROOT/'parent-results.json',state)
 tasks=json.loads((BASE/'tasks.json').read_text());tasks['tasks']=[t for t in tasks['tasks'] if t['name'] in {t for t,a in AUTHORIZED}]
 tasks['selection']='Only seven explicitly authorized engineering failures from the original paired sample'
 atomic_json(ROOT/'tasks.json',tasks);atomic_json(ROOT/'history.json',{})
 rows=initial_rows([t['name'] for t in tasks['tasks']],{});atomic_json(ROOT/'repair-queue.json',rows)
 profile=json.loads((BASE/'budget-profile.json').read_text());profile['jobs']=[r['job'] for r in rows]
 assert profile['campaign_limit_microcny']==80000000 and profile['task_limit_microcny']==4000000
 atomic_json(ROOT/'budget-profile.json',profile)
 source=sqlite3.connect('file:'+str(BASE/'spending.sqlite')+'?mode=ro',uri=True);target=sqlite3.connect(ROOT/'spending.sqlite');source.backup(target)
 before=target.execute('select * from calls order by id').fetchall()
 target.execute("update meta set value=? where key='profile'",(json.dumps(profile,sort_keys=True),));target.commit()
 assert before==target.execute('select * from calls order by id').fetchall()
 imported=target.execute("select sum(case when state='settled' then actual else reserved end) from calls").fetchone()[0]
 pending=target.execute("select count(*),coalesce(sum(reserved),0) from calls where state='reserved'").fetchone()
 source.close();target.close()
 atomic_json(ROOT/'budget-migration.json',dict(parent=str(BASE),imported_calls=len(before),imported_charged_microcny=imported,campaign_limit_microcny=80000000,old_pending_calls=pending[0],old_pending_microcny=pending[1],old_pending_policy='Retain full reservation; convert to unknown on new supervisor start, never refund automatically'))
 protocol=json.loads((BASE/'protocol.json').read_text());protocol.update(parent_runtime=str(BASE),paired_tasks=5,engineering_revision='paired-repair-2',arm_order='Seven selected faulty arm/task pairs; at most two total and one per arm',tasks_sha256=sha(ROOT/'tasks.json'),status='offline_acceptance_pending',comparison_limit='Original outcomes retained; selective engineering rerun, not a new independent ten-task sample',bounded_design=profile,verifier_repair='Official uv0.9.5 and its CPython3.13 runtime prefetched; verifier-only dependency bootstrap and stale HTTP apt cache prevention; official tests unchanged')
 protocol.update(protocol_fields(load(ROOT)));atomic_json(ROOT/'protocol.json',protocol)
 atomic_json(ROOT/'ready.json',dict(passed=False));print(json.dumps(dict(prepared=True,trials=7,charged_microcny=imported,remaining_microcny=80000000-imported)))
if __name__=='__main__':main()
