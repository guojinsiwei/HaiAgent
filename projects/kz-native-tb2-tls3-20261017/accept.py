import os,json,sys,uuid,time,subprocess,hashlib
from pathlib import Path
from campaign import ROOT,command,trial
from storage import atomic_json
from validate import hashes

def main():
    label=sys.argv[1] if len(sys.argv)>1 else 'accept-timeout'
    row=dict(task='build-cython-ext',arm='native-kz',job=label,preflight_attempt_id=uuid.uuid4().hex)
    cmd=command(row,True);cmd[cmd.index('agents:OfflineNative')]='agents:OfflineTimeout'
    env=dict(os.environ,PYTHONPATH=str(ROOT),PAIRED_TASK=row['task'],PAIRED_ATTEMPT_ID=row['preflight_attempt_id'],PYTHONDONTWRITEBYTECODE='1')
    for k in list(env):
        if k.endswith(('API_KEY','AUTH_TOKEN')):env.pop(k)
    with (ROOT/(label+'.log')).open('xb') as f:result=subprocess.run(cmd,env=env,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=f,stderr=f)
    out=trial(row,True);out.update(harbor_exit=result.returncode,paid_calls=0)
    p=Path(out['trial']);live=p/'agent/live'
    out['private_readable']=(live/'private-probe.txt').exists() and (live/'private-probe.txt').read_text()=='offline private probe'
    out['exit']=json.loads((live/'agent-exit.json').read_text()) if (live/'agent-exit.json').exists() else {}
    out['passed']=bool(out['engineering_clean'] and result.returncode==0 and out['private_readable'] and out['exit'].get('timed_out'))
    out['source_hashes']=hashes()
    out['runtime_sha256']=hashlib.sha256((ROOT/'native-runtime.tar.gz').read_bytes()).hexdigest()
    atomic_json(ROOT/(label+'-result.json'),out);print(json.dumps(out));return 0 if out['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
