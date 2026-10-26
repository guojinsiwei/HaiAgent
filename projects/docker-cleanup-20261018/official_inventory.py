import hashlib,json,subprocess,time,shutil
from pathlib import Path
TASK_HOME=Path('/mnt/sdb/home/lizh639')
P=TASK_HOME/'tb2-three-arm50-20261017';C=TASK_HOME/'tb2-three-arm50-retry2-20261018';A=TASK_HOME/'docker-cleanup-20261018'
def run(*args):return subprocess.check_output(args,text=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
health=json.loads((C/'health.json').read_text())
needed={r['task'] for r in health['rows'] if r['state'] not in ('done','engineering_failure','historical')}
parent=json.loads((P/'health.json').read_text());evidence={}
for row in parent['rows']:
 t=Path(row.get('result',{}).get('trial','/missing'));p=t/'agent/image-check.json'
 if not p.exists() or not (t/'result.json').exists():continue
 for ids in json.loads(p.read_text()).get('image_ids',{}).values():
  for ident in ids:evidence.setdefault(ident,[]).append(dict(task=row['task'],trial=str(t),sha256=sha(t/'result.json')))
ids=run('docker','ps','-aq').split();containers=json.loads(run('docker','inspect',*ids)) if ids else []
used={c['Image'] for c in containers};candidates=[]
for ident,proof in evidence.items():
 if any(r['task'] in needed for r in proof) or ident in used:continue
 p=subprocess.run(['docker','image','inspect',ident],capture_output=True,text=True)
 if p.returncode:continue
 image=json.loads(p.stdout)[0];tags=image.get('RepoTags') or []
 allowed={'alexgshaw/'+r['task']+':20251031' for r in proof}
 if not tags or not set(tags)<=allowed:continue
 candidates.append(dict(id=ident,tags=tags,size=image['Size'],evidence=proof))
report=dict(needed_tasks=sorted(needed),candidates=candidates,free_before=shutil.disk_usage('/var/lib/docker').free,created=time.time())
(A/'official-inventory.json').write_text(json.dumps(report,indent=2))
print(json.dumps(dict(candidates=len(candidates),nominal_GiB=round(sum(r['size'] for r in candidates)/1024**3,2),tags=[r['tags'] for r in candidates],protected_tasks=sorted(needed)),indent=2))
