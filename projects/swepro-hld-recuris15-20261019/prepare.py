"""Freeze a paired SWE-Pro V2 campaign; no provider calls."""
from pathlib import Path
import collections,hashlib,json,random,shutil,subprocess,tarfile,tomllib
R=Path(__file__).resolve().parent
def save(p,x): p.write_text(json.dumps(x,indent=2))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def select_tasks():
 upstream=R/'upstream'; tasks=upstream/'v2/tasks'
 commit=subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
 buckets=collections.defaultdict(list)
 for p in sorted(tasks.iterdir()):
  # instance_<owner>__<repository>-<40-character commit>-<suffix>
  import re
  repo=re.split(r'-[0-9a-f]{40}(?:-|$)',p.name)[0].removeprefix('instance_')
  buckets[repo].append(p)
 assert len(buckets)==11, f'Expected 11 repositories, got {len(buckets)}'
 rng=random.Random(20261019)
 selected=[]
 for repo in sorted(buckets):
  rng.shuffle(buckets[repo]);selected.append(buckets[repo].pop())
 remaining=sorted(p for values in buckets.values() for p in values);rng.shuffle(remaining)
 selected+=remaining[:15-len(selected)];rng.shuffle(selected)
 assert len(selected)==15 and len(set(selected))==15
 manifest=[]
 for i,p in enumerate(selected,1):
  cfg=tomllib.loads((p/'task.toml').read_text())
  dest=R/'tasks'/p.name;shutil.copytree(p,dest,dirs_exist_ok=True)
  manifest.append(dict(index=i,name=p.name,image=cfg['environment']['docker_image'],environment=cfg['environment'],files={str(f.relative_to(dest)):digest(f) for f in dest.rglob('*') if f.is_file()}))
 save(R/'tasks.json',dict(benchmark='SWE-bench Pro V2',commit=commit,seed=20261019,selection='one per repository, then four uniformly shuffled remaining tasks; frozen before outcomes',tasks=manifest))
 return manifest,commit
def main():
 assert not (R/'prepared.json').exists()
 old=R.parent/'tb2-hld-old-new10-20261019'
 manifest,commit=select_tasks()
 shutil.copytree(old/'bundle',R/'bundle',symlinks=True,ignore=shutil.ignore_patterns('hld-old'))
 bundle=R/'bundle'
 for name in ['spending.py','storage.py','test_bounded_ledger.py']:
  shutil.copy2(old/name,R/name)
 with tarfile.open(old/'python-runtime.tar.gz') as archive:
  archive.extractall(R/'python-extract',filter='data')
 python=next((R/'python-extract').iterdir());python.rename(bundle/'kz-python')
 shutil.copy2(R/'container-run.mjs',bundle/'kz/container-run.mjs')
 shutil.copy2(R/'socket-relay.mjs',bundle/'kz/socket-relay.mjs')
 p=bundle/'kz/.runtime/kz.patch.yml';p.write_text(p.read_text().replace('limitCny: 4','limitCny: 8').replace('wallSeconds: 7200','wallSeconds: 3000'))
 p=bundle/'kz/shared-budget.mjs';p.write_text(p.read_text().replace('estimatePeakCny:4','estimatePeakCny:8').replace('seconds:7200','seconds:3000'))
 jobs=[f'swp-{t["index"]:02}-{a}' for t in manifest for a in ('hld','recuris')]
 profile=json.loads((old/'budget-profile.json').read_text());profile.update(campaign_limit_microcny=240000000,task_limit_microcny=8000000,solver_seconds=3000,jobs=jobs)
 save(R/'budget-profile.json',profile)
 lock={str(p.relative_to(bundle)):digest(p) for folder in ['kz/src','recuris-dsh/src','dsh-baselines/src'] for p in (bundle/folder).rglob('*') if p.is_file()}
 save(R/'source-lock.json',lock)
 save(R/'protocol.json',dict(benchmark='SWE-bench Pro V2',commit=commit,task_count=15,runs=30,model='deepseek-flash',temperature=0,thinking=False,per_run_cny=8,total_cny=240,solver_seconds=3000,concurrency=4,per_arm_concurrency=2,arms=['HLD v6 latest TB2 candidate','Recuris repaired v5 latest deployment'],agent_network='none; Unix socket relay allows only TaoToken API and budget service',evaluation='original verifier in pristine image with captured patch only',preflight='empty patch fails and gold patch passes; failed task gated without blocking other tasks',automatic_paid_retries=False,cross_task_memory=False,budget_basis='existing peak token prices; not a TaoToken Credits invoice',selection='seeded repository-stratified public V2 subset'))
 save(R/'prepared.json',dict(passed=True,paid_calls=0,commit=commit))
 print('Prepared 15 paired tasks; 240 CNY ceiling; zero model calls')
if __name__=='__main__':main()
