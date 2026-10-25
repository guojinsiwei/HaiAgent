"""Deploy a source-only repair under the stopped campaign's supervisor lock."""
import datetime, fcntl, hashlib, json, os, shutil, sqlite3, subprocess
from pathlib import Path

STAGE=Path('/mnt/sdb/home/lizh639/tb4-ctyun-repair-20261016-r1')
ROOT=Path('/mnt/sdb/home/lizh639/tb4-ctyun-firstpass-20261015')
PY='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ledger_digest():
    db=sqlite3.connect((ROOT/'spending.sqlite').as_uri()+'?mode=ro',uri=True)
    try:return hashlib.sha256('\n'.join(db.iterdump()).encode()).hexdigest()
    finally:db.close()
def audit():
    return json.loads(subprocess.run([PY,str(STAGE/'audit_campaign.py'),str(ROOT)],check=True,capture_output=True,text=True).stdout)
def atomic_copy(source,target):
    tmp=target.with_name(target.name+'.repair-tmp')
    shutil.copyfile(source,tmp);os.replace(tmp,target)

manifest=json.loads((STAGE/'repair-manifest.json').read_text(encoding='utf-8-sig'))
with (ROOT/'supervisor.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    health=json.loads((ROOT/'health.json').read_text())
    assert health['state']=='stopped' and not health['active'] and not health.get('winner')
    assert not Path('/proc/'+str(health['pid'])).exists(),'Supervisor still running'
    assert json.loads((ROOT/'budget-profile.json').read_text())['campaign_limit_fen']==3000
    assert digest(ROOT/'ready.json')==manifest['ready_before'],'Deployment receipt changed'
    for row in manifest['files']:
        name=row['name'];assert Path(name).name==name and Path(name).suffix in ('.py','.mjs')
        assert digest(STAGE/name)==row['after']
        assert (digest(ROOT/name) if (ROOT/name).exists() else None)==row['before'],'Source changed: '+name
    before=dict(health_sha256=digest(ROOT/'health.json'),ledger_sha256=ledger_digest(),audit=audit())
    backup=ROOT/'engineering-repair-backup-20261016'
    backup.mkdir(exist_ok=False)
    shutil.copyfile(ROOT/'ready.json',backup/'ready.json')
    for row in manifest['files']:
        if row['before']:shutil.copyfile(ROOT/row['name'],backup/row['name'])
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
    try:
        for row in manifest['files']:atomic_copy(STAGE/row['name'],ROOT/row['name'])
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        checked=subprocess.run([PY,str(ROOT/'seal.py')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=120)
        (STAGE/'deployment-tests.log').write_text(checked.stdout+checked.stderr)
        checked.check_returncode()
        subprocess.run([PY,str(ROOT/'run.py'),'precheck'],cwd=ROOT,env=env,check=True,capture_output=True,text=True,timeout=30)
        after=dict(health_sha256=digest(ROOT/'health.json'),ledger_sha256=ledger_digest(),audit=audit())
        assert before==after,'Protected campaign state changed'
        receipt=dict(deployed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            state='repaired_stopped',paid_calls=0,tests=dict(node=20,python=21),
            protected_state_unchanged=True,before=before,after=after,files=manifest['files'])
        (STAGE/'repair-receipt.json').write_text(json.dumps(receipt,indent=2))
        (ROOT/'engineering-repair-receipt.json').write_text(json.dumps(receipt,indent=2))
        print(json.dumps({k:receipt[k] for k in ('state','paid_calls','tests','protected_state_unchanged')}))
    except BaseException:
        for row in manifest['files']:
            target=ROOT/row['name']
            if row['before']:atomic_copy(backup/row['name'],target)
            elif target.exists():target.unlink()
        atomic_copy(backup/'ready.json',ROOT/'ready.json')
        raise
