"""User-authorized cleanup of old, unreferenced Compose trial images."""
import datetime,json,shutil,subprocess,sys,time
from pathlib import Path
A=Path('/mnt/sdb/home/lizh639/docker-cleanup-20261018');TARGET=180*1024**3
def run(*args):return subprocess.run(args,text=True,capture_output=True,timeout=180)
def references():
 p=run('docker','ps','-aq');assert p.returncode==0
 if not p.stdout.split():return [],set(),set()
 p=run('docker','inspect',*p.stdout.split());assert p.returncode==0
 rows=json.loads(p.stdout)
 return rows,{r['Image'] for r in rows},{(r['Config'].get('Labels') or {}).get('com.docker.compose.project') for r in rows}
def eligible(i,used,projects):
 tags=i.get('RepoTags') or [];project=(i['Config'].get('Labels') or {}).get('com.docker.compose.project','')
 created=datetime.datetime.fromisoformat(i['Created'].replace('Z','+00:00')).timestamp()
 return bool(tags and all(t.startswith('skillsbench-no-skills/') for t in tags) and i['Id'] not in used and (not project or project not in projects) and time.time()-created>86400)
if '--clean' not in sys.argv:
 containers,used,projects=references();p=run('docker','image','ls','-q','--no-trunc');assert p.returncode==0
 ids=list(dict.fromkeys(p.stdout.split()));candidates=[]
 for n in range(0,len(ids),80):
  result=run('docker','image','inspect',*ids[n:n+80]);assert result.returncode==0
  for i in json.loads(result.stdout):
   if eligible(i,used,projects):candidates.append(dict(id=i['Id'],tags=i['RepoTags'],size=i['Size'],created=i['Created']))
 (A/'unused-skills-inventory.json').write_text(json.dumps(dict(candidates=candidates,protected_containers=[r['Id'] for r in containers],created=time.time()),indent=2))
 print(json.dumps(dict(candidates=len(candidates),nominal_GiB=sum(r['size'] for r in candidates)/1024**3,sample=candidates[:3])))
else:
 inventory=json.loads((A/'unused-skills-inventory.json').read_text());out=dict(started=time.time(),free_before=shutil.disk_usage('/var/lib/docker').free,removed=[],skipped=[])
 def save():(A/'unused-skills-result.json').write_text(json.dumps(out,indent=2))
 save()
 for row in sorted(inventory['candidates'],key=lambda x:x['size'],reverse=True):
  if shutil.disk_usage('/var/lib/docker').free>=TARGET:break
  p=run('docker','image','inspect',row['id'])
  if p.returncode:continue
  i=json.loads(p.stdout)[0];_,used,projects=references()
  if not eligible(i,used,projects) or set(i.get('RepoTags') or [])!=set(row['tags']):out['skipped'].append(row['id']);continue
  result=run('docker','image','rm',*row['tags'])
  entry=dict(id=row['id'],tags=row['tags'],exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
  (out['removed'] if result.returncode==0 else out['skipped']).append(entry)
  out['free_after']=shutil.disk_usage('/var/lib/docker').free;save()
  print(json.dumps(dict(removed=len(out['removed']),free_GiB=out['free_after']/1024**3)),flush=True)
 out.update(finished=time.time(),free_after=shutil.disk_usage('/var/lib/docker').free);save()
 print(json.dumps(dict(finished=True,removed=len(out['removed']),free_GiB=out['free_after']/1024**3)))

