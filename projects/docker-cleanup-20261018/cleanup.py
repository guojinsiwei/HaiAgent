"""Remove only inventoried, completed own-trial build images; no containers or volumes."""
import json,subprocess,hashlib,shutil,time
from pathlib import Path
TASK_HOME=Path('/mnt/sdb/home/lizh639').resolve();AUDIT=TASK_HOME/'docker-cleanup-20261018'
CURRENT=TASK_HOME/'tb2-three-arm50-retry2-20261018';TARGET=180*1024**3
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*args):return subprocess.run(args,capture_output=True,text=True,timeout=120)
def save(value):(AUDIT/'cleanup-result.json').write_text(json.dumps(value,indent=2))
report=json.loads((AUDIT/'inventory.json').read_text())
out=dict(started=time.time(),before_free=shutil.disk_usage('/var/lib/docker').free,target_free=TARGET,removed=[],skipped=[],history_verified=False)
save(out)
for row in sorted(report['candidates'],key=lambda r:r['size'],reverse=True):
    if shutil.disk_usage('/var/lib/docker').free>=TARGET:break
    trial=Path(row['trial']['path']).resolve()
    if not trial.is_relative_to(TASK_HOME) or trial.is_relative_to(CURRENT):raise RuntimeError('Trial ownership/path mismatch')
    if sha(trial/'result.json')!=row['trial']['result_sha256']:raise RuntimeError('Historical result changed; stopping cleanup')
    inspect=run('docker','image','inspect',row['id'])
    if inspect.returncode:out['skipped'].append(dict(id=row['id'],reason='already_absent'));continue
    current=json.loads(inspect.stdout)[0];tags=current.get('RepoTags') or []
    if set(tags)!=set(row['tags']):out['skipped'].append(dict(id=row['id'],reason='references_changed'));continue
    ids=run('docker','ps','-aq').stdout.split()
    containers=json.loads(run('docker','inspect',*ids).stdout) if ids else []
    if any(c['Image']==row['id'] for c in containers):out['skipped'].append(dict(id=row['id'],reason='container_reference'));continue
    before=shutil.disk_usage('/var/lib/docker').free
    # Explicit tags only, never -f, never system/image/volume prune.
    result=run('docker','image','rm',*tags)
    after=shutil.disk_usage('/var/lib/docker').free
    entry=dict(id=row['id'],tags=tags,trial=str(trial),exit_code=result.returncode,observed_free_delta=after-before,output=result.stdout,stderr=result.stderr)
    (out['removed'] if result.returncode==0 else out['skipped']).append(entry)
    out['after_free']=after;save(out)
    print(json.dumps(dict(processed=len(out['removed']),free_GiB=round(after/1024**3,2),exit_code=result.returncode)),flush=True)
for row in report['candidates']:
    if sha(Path(row['trial']['path'])/'result.json')!=row['trial']['result_sha256']:raise RuntimeError('Historical result hash mismatch')
out.update(finished=time.time(),after_free=shutil.disk_usage('/var/lib/docker').free,history_verified=True)
save(out)
print(json.dumps(dict(finished=True,removed=len(out['removed']),skipped=len(out['skipped']),free_GiB=round(out['after_free']/1024**3,2),historical_result_hashes_verified=True)),flush=True)

