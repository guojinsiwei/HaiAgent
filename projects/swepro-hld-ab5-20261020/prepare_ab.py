"""Prepare a fresh paired HLD comparison, without any provider calls."""
import hashlib,json,sqlite3,time
from pathlib import Path
R=Path(__file__).resolve().parent
OLD=R.parent/'swepro-hld-recuris15-20261019'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,indent=2))
def main():
 assert not (R/'prepared-ab.json').exists()
 assert read(OLD/'health.json')['state']=='finished'
 profile=read(OLD/'budget-profile.json')
 with sqlite3.connect(OLD/'spending.sqlite') as db:
  rows=db.execute('select * from calls order by id').fetchall()
  charged=db.execute("select coalesce(sum(case when state='settled' then actual else reserved end),0) from calls").fetchone()[0]
  count=len(rows)
 assert charged+80000000<=profile['campaign_limit_microcny']
 indices=read(R/'selection.json')['indices']
 assert len(set(indices))==5
 profile.update(campaign_limit_microcny=80000000,jobs=[f'swp-{i:02}-{a}' for i in indices for a in ('old','new')])
 save(R/'budget-profile.json',profile)
 save(R/'budget-allocation.json',dict(original_total_cap_microcny=240000000,original_charged_including_reservations=charged,
  comparison_cap_microcny=80000000,combined_max_microcny=charged+80000000,original_calls=count,
  original_calls_sha256=hashlib.sha256(json.dumps(rows).encode()).hexdigest(),original_ledger_unchanged=True,
  rule='80 CNY allocated from unspent original 240 CNY envelope; original campaign is finished, no original paid restart allowed during comparison. Unsettled reservations remain charged.'))
 s=(R/'runner.py').read_text()
 s=s.replace("LABEL='swepro-hld-recuris15-20261019'","LABEL='swepro-hld-ab5-20261020'")
 s=s.replace('def install_mounts(services):','def install_mounts(services,arm="old"):')
 s=s.replace("/d,'/opt/'+d,True)","/('hld-new' if d=='kz' and arm=='new' else d),'/opt/'+d,True)")
 s=s.replace('mounts=install_mounts(services))','mounts=install_mounts(services,arm))')
 s=s.replace("dict(arm=arm,key=key,instruction=instruction","dict(arm='hld',key=key,instruction=instruction")
 s=s.replace("CAMPAIGN_BUDGET_ARM='kz' if arm=='hld' else 'dsh'","CAMPAIGN_BUDGET_ARM='kz'")
 s=s.replace("hld_monetary_stop(folder/'live',arm,bool(exit_doc),code)","hld_monetary_stop(folder/'live','hld',bool(exit_doc),code)")
 # Official scoring and execution termination have separate status fields.
 s=s.replace("engineering_clean=clean,budget_stop=stop","engineering_clean=clean,official_score_valid=scored['engineering_clean'],budget_stop=stop")
 (R/'runner.py').write_text(s)
 lock={str(p.relative_to(R/'bundle')):hashlib.sha256(p.read_bytes()).hexdigest()
  for folder in ['kz/src','hld-new/src','recuris-dsh/src','dsh-baselines/src']
  for p in (R/'bundle'/folder).rglob('*') if p.is_file()}
 oldlock=read(OLD/'source-lock.json')
 assert all(lock[k]==v for k,v in oldlock.items())
 save(R/'source-lock.json',lock)
 save(R/'protocol.json',dict(benchmark='SWE-bench Pro V2',task_indices=indices,arms=['old','new'],runs=10,
  selection='Four HLD failures plus one random previously passed task; seed 20261020, Element task 10. Diagnostic development comparison, not held-out generalization.',
  model='deepseek-flash',temperature=0,per_run_cny=8,total_comparison_cny=80,original_envelope_cny=240,
  requests_per_task=400,tools_per_task=600,solver_seconds=3000,concurrency=4,
  baseline='Exact frozen HLD deployed in original SWE-Pro run',
  candidate='Generic role protocol, structured-data rendering, public contract and repeated-failure replanning repairs',
  same_environment='Same original image, instruction, dependency cache preparation, CPU=1, memory=8GB, source state and official verifier',
  evaluation='Fresh isolated container with only captured patch and original official tests; no prior task patch, audit or grading output given to solver',
  automatic_paid_retries=False,algorithm_source_frozen=True,cross_task_memory=False))
 save(R/'prepared-ab.json',dict(time=time.time(),paid_calls=0,passed=True))
 print('Prepared ten paired runs, 80 CNY ceiling within original 240 CNY total')
if __name__=='__main__':main()
