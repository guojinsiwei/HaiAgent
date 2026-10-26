"""Exercise all three adapters with scripted replies and original official grading."""
import concurrent.futures,hashlib,json,os,subprocess,sys,tarfile,uuid
from pathlib import Path
from campaign import ROOT,command,trial
from build_runtime import build
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def one(arm):
    row=dict(task='build-cython-ext',arm=arm,job='accept-'+arm,preflight_attempt_id=uuid.uuid4().hex)
    env=dict(os.environ,PYTHONPATH=str(ROOT),PAIRED_TASK=row['task'],PAIRED_ATTEMPT_ID=row['preflight_attempt_id'],PYTHONDONTWRITEBYTECODE='1')
    for k in list(env):
        if k.endswith(('API_KEY','AUTH_TOKEN')):env.pop(k,None)
    with (ROOT/('accept-'+arm+'.log')).open('x') as log:
        p=subprocess.run(command(row,True),env=env,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,timeout=1800)
    result=trial(row,True);result.update(arm=arm,exit_code=p.returncode,paid_calls=0)
    (ROOT/('accept-'+arm+'.json')).write_text(json.dumps(result,indent=2))
    return result
def main():
    build()
    with tarfile.open(ROOT/'native-runtime.tar.gz','w:gz') as tar:
        tar.add(ROOT/'native',arcname='kz-standalone',filter=lambda i:None if '__pycache__' in i.name or '/test-tmp' in i.name else i)
    with concurrent.futures.ThreadPoolExecutor(3) as pool:results=list(pool.map(one,['native-kz','kz-dsh','dsh']))
    print(json.dumps(results));return 0 if all(r['engineering_clean'] and r['exit_code']==0 for r in results) else 1
if __name__=='__main__':raise SystemExit(main())
