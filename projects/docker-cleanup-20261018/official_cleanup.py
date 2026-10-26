import hashlib,json,shutil,subprocess,time
from pathlib import Path
A=Path('/mnt/sdb/home/lizh639/docker-cleanup-20261018')
C=A.parent/'tb2-three-arm50-retry2-20261018'
def run(*args):return subprocess.run(args,text=True,capture_output=True,timeout=120)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inventory=json.loads((A/'official-inventory.json').read_text())
out=dict(started=time.time(),free_before=shutil.disk_usage('/var/lib/docker').free,removed=[],skipped=[])
def save():(A/'official-cleanup-result.json').write_text(json.dumps(out,indent=2))
save()
for row in inventory['candidates']:
 health=json.loads((C/'health.json').read_text())
 needed={r['task'] for r in health['rows'] if r['state'] not in ('done','engineering_failure','historical')}
 if any(p['task'] in needed for p in row['evidence']):raise RuntimeError('Task became active/pending')
 for p in row['evidence']:
  path=Path(p['trial'])/'result.json'
  if not path.resolve().is_relative_to(A.parent) or sha(path)!=p['sha256']:raise RuntimeError('Historical result changed')
 inspected=run('docker','image','inspect',row['id'])
 if inspected.returncode:out['skipped'].append(dict(id=row['id'],reason='absent'));continue
 current=json.loads(inspected.stdout)[0]
 if set(current.get('RepoTags') or [])!=set(row['tags']):raise RuntimeError('Image references changed')
 ids=run('docker','ps','-aq').stdout.split()
 containers=json.loads(run('docker','inspect',*ids).stdout) if ids else []
 if any(c['Image']==row['id'] for c in containers):out['skipped'].append(dict(id=row['id'],reason='container_reference'));continue
 result=run('docker','image','rm',*row['tags'])
 entry=dict(id=row['id'],tags=row['tags'],exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
 (out['removed'] if result.returncode==0 else out['skipped']).append(entry);save()
for row in inventory['candidates']:
 for p in row['evidence']:assert sha(Path(p['trial'])/'result.json')==p['sha256']
out.update(finished=time.time(),free_after=shutil.disk_usage('/var/lib/docker').free,history_verified=True);save()
print(json.dumps(dict(removed=len(out['removed']),skipped=len(out['skipped']),free_before_GiB=out['free_before']/1024**3,free_after_GiB=out['free_after']/1024**3,history_verified=True)))
