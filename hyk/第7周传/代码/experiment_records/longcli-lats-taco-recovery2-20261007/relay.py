"""Local no-model file relay; public status and immutable final artifacts only."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parent
KEY='C:/Users/54177/.ssh/cubestudio_notebook'
COLLEGE='lizh639@172.16.108.236'
DEST='/var/tmp/lizh639-longcli-lats-taco-recovery2-20261007/taco'
PY='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
CUBE_PY='/mnt/lizh639/longcli-retrac20-matched-20261006/test-env/bin/python'

def run(args):
    r=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
    if r.returncode:raise RuntimeError('transport_exit_'+str(r.returncode))
    return r.stdout
def ssh(host,command):return run(['ssh','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=10',host,command])
def scp(source,destination):return run(['scp','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=10',source,destination])
def save(name,value):
    p=ROOT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(value,indent=2));t.replace(p)

def main():
    import msvcrt
    lock=(ROOT/'relay.lock').open('a+b');lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    receipt=ROOT/'relay-receipts.json';done=json.loads(receipt.read_text()) if receipt.exists() else {}
    ssh(COLLEGE,f'{PY} -B {DEST}/relay_receiver.py --start')
    while True:
        errors=[];snapshots=[]
        for worker,host in enumerate(('cubestudio_container','cubestudio_container2')):
            remote=f'/mnt/lizh639/longcli-taco-recovery2-worker{worker}-20261007'
            try:
                status=json.loads(ssh(host,f'{CUBE_PY} -B {remote}/status_public.py'));snapshots.append(status)
                for row in status['jobs']:
                    job=row['job']
                    if not row['summary'] or job in done:continue
                    target=ROOT/'received'/job;target.mkdir(parents=True,exist_ok=True)
                    scp(f'{host}:{remote}/jobs/{job}/summary.json',str(target/'summary.json'))
                    summary=json.loads((target/'summary.json').read_text())
                    assert summary['job']==job
                    if summary['state']=='awaiting_grade':
                        scp(f'{host}:{remote}/jobs/{job}/final-source.tar.gz',str(target/'final-source.tar.gz'))
                        assert hashlib.sha256((target/'final-source.tar.gz').read_bytes()).hexdigest()==row['artifact_sha256']
                    stage=f'{DEST}/relay-staging/{job}'
                    ssh(COLLEGE,f'mkdir -p {stage}')
                    scp(str(target/'summary.json'),f'{COLLEGE}:{stage}/summary.json')
                    if summary['state']=='awaiting_grade':scp(str(target/'final-source.tar.gz'),f'{COLLEGE}:{stage}/final-source.tar.gz')
                    reply=json.loads(ssh(COLLEGE,f'{PY} -B {DEST}/relay_receiver.py {job}'))
                    done[job]={'time':time.time(),'state':summary['state'],'receipt':reply};save('relay-receipts.json',done)
            except Exception as error:errors.append({'host':host,'error_type':type(error).__name__})
        save('relay-health.json',{'state':'all_deliveries_transferred' if len(done)==5 else 'watching',
            'updated':time.time(),'received':len(done),'expected':5,'errors':errors,'workers':snapshots,'model_calls':0})
        if len(done)==5:return
        time.sleep(30)

if __name__=='__main__':main()
