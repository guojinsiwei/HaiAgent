"""Inventory only: map regenerable Compose images to this user's completed trials."""
import os,json,subprocess,hashlib,time
from pathlib import Path
TASK_HOME=Path('/mnt/sdb/home/lizh639')
CURRENT=TASK_HOME/'tb2-three-arm50-retry2-20261018'
AUDIT=TASK_HOME/'docker-cleanup-20261018';AUDIT.mkdir(exist_ok=True)
def cmd(*args):return subprocess.check_output(args,text=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
skip={'.git','node_modules','venv','.venv','runtime','native','dependencies','official-source','upstream','__pycache__','sources','site-packages','snapshots','workspace','workspaces','artifacts'}
trials={}
for project in TASK_HOME.iterdir():
    if not project.is_dir() or project in (CURRENT,AUDIT) or project.name.startswith('.'):continue
    for folder,dirs,files in os.walk(project):
        dirs[:]=[d for d in dirs if d not in skip and not (Path(folder)/d).is_symlink()]
        if len(Path(folder).relative_to(project).parts)>7:dirs[:]=[]
        if 'result.json' not in files or '__' not in Path(folder).name:continue
        p=Path(folder)/'result.json'
        try:r=json.loads(p.read_text())
        except (ValueError,OSError):continue
        if not isinstance(r,dict) or not r.get('finished_at'):continue
        trials[Path(folder).name.lower()]=dict(path=str(Path(folder)),result_sha256=sha(p),finished_at=r['finished_at'])
        dirs[:]=[]  # Trial logs/artifacts are historical outputs, never cleanup targets.
print(json.dumps(dict(completed_trials_found=len(trials))),flush=True)
container_ids=cmd('docker','ps','-aq').split()
containers=json.loads(cmd('docker','inspect',*container_ids)) if container_ids else []
used={c['Image'] for c in containers};activeprojects={(c['Config'].get('Labels') or {}).get('com.docker.compose.project') for c in containers}
listed=[json.loads(line) for line in cmd('docker','image','ls','--no-trunc','--format','{{json .}}').splitlines()]
prefixes=tuple(n+s for n in trials for s in ('__env-','__verifier__trial-'))
ids=list(dict.fromkeys(i['ID'] for i in listed if i['Repository'].startswith(prefixes)))
print(json.dumps(dict(matching_image_ids=len(ids))),flush=True)
candidates=[];images=[]
for start in range(0,len(ids),100):
    for i in json.loads(cmd('docker','image','inspect',*ids[start:start+100])):
        tags=i.get('RepoTags') or [];labels=i['Config'].get('Labels') or {};project=labels.get('com.docker.compose.project','')
        row=dict(id=i['Id'],tags=tags,created=i['Created'],size=i['Size'],project=project)
        images.append(row)
        if i['Id'] in used or project in activeprojects or not tags:continue
        for name,trial in trials.items():
            # Names of completed historical trials only; never current-run or shared base tags.
            if project in (name+'__env',name+'__verifier__trial') and all(t.split(':')[0].startswith(project+'-') for t in tags):
                candidates.append(dict(**row,trial=trial));break
report=dict(created=time.time(),trials_found=len(trials),container_count=len(containers),protected_container_ids=[c['Id'] for c in containers],candidates=candidates)
(AUDIT/'inventory.json').write_text(json.dumps(report,indent=2))
(AUDIT/'images-before.json').write_text(json.dumps(images,indent=2))
print(json.dumps(dict(trials_found=len(trials),candidates=len(candidates),nominal_GiB=round(sum(i['size'] for i in candidates)/1024**3,2),sample=[dict(tags=i['tags'],trial=i['trial']['path']) for i in candidates[:8]]),indent=2))


