"""Upload source-only bundles; preflight without API calls. No credentials read."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parent/'longcli-dhv1-os10-20261004'
NAME=ROOT.name
KEY='C:/Users/54177/.ssh/cubestudio_notebook'
COLLEGE='lizh639@172.16.108.236'
CUBE='root@172.16.108.241'
PROXY='ProxyCommand=ssh -i '+KEY+' -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p '+COLLEGE
PY='/mnt/lizh639/envs/swe-eval/bin/python'
CPY='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
CR='/var/tmp/lizh639-'+NAME
SR='/mnt/lizh639/'+NAME

def call(args):
    subprocess.run(args,check=True,timeout=600)

def ssh(worker,cmd):
    args=['ssh','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15']
    if worker is None:args += [COLLEGE,cmd]
    else:args += ['-p',('31081','31121')[worker],'-o',PROXY,CUBE,cmd]
    call(args)

def main(stage):
    if stage=='upload':
        shutil.copy2(ROOT.parent/'dhv1_os10_setup.py',ROOT/'setup_campaign.py')
        for kind in ('solver','college'):
            with tarfile.open(ROOT/(kind+'-deployment.tgz'),'w:gz') as archive:
                files=[f for f in ROOT.glob('*') if f.suffix in ('.py','.json')]
                if kind=='solver':files += [f for folder in ('sources','compatibility') for f in (ROOT/folder).rglob('*') if f.is_file()]
                for f in files:archive.add(f,arcname=f.relative_to(ROOT).as_posix(),recursive=False)
        ssh(None,'mkdir '+CR)
        call(['scp','-i',KEY,'-o','BatchMode=yes',str(ROOT/'college-deployment.tgz'),COLLEGE+':'+CR+'/deployment.tgz'])
        ssh(None,'tar -xzf '+CR+'/deployment.tgz -C '+CR+' && cd '+CR+' && '+CPY+' -B setup_campaign.py college && '+CPY+' -B validate_college.py')
        ssh(0,'mkdir '+SR)
        call(['scp','-i',KEY,'-P','31081','-o','BatchMode=yes','-o',PROXY,str(ROOT/'solver-deployment.tgz'),CUBE+':'+SR+'/deployment.tgz'])
        ssh(0,'tar -xzf '+SR+'/deployment.tgz -C '+SR+' && cd '+SR+' && '+PY+' -B setup_campaign.py solver')
        ssh(1,'test -f '+SR+'/protocol.json && test -d '+SR+'/public && echo shared_campaign_ready')
    elif stage=='preflight':
        children=[]
        for worker in (0,1):
            cmd='cd '+SR+' && '+PY+' -B cube_prepare.py --worker '+str(worker)+' > solver-preflight-'+str(worker)+'.log 2>&1'
            children.append(subprocess.Popen(['ssh','-i',KEY,'-p',('31081','31121')[worker],'-o','BatchMode=yes','-o','ConnectTimeout=15','-o',PROXY,CUBE,cmd]))
        for process in children:
            code=process.wait(timeout=600)
            if code:raise RuntimeError('Offline preflight failed; no model run started')
        ssh(0,'cd '+SR+' && '+PY+' -B setup_campaign.py seal && '+PY+' -B validate.py')
        call(['scp','-i',KEY,'-P','31081','-o','BatchMode=yes','-o',PROXY,CUBE+':'+SR+'/preflight-0.json',str(ROOT/'preflight-0.json')])
        call(['scp','-i',KEY,'-P','31081','-o','BatchMode=yes','-o',PROXY,CUBE+':'+SR+'/preflight-1.json',str(ROOT/'preflight-1.json')])
    else:raise ValueError(stage)
    print(json.dumps(dict(stage=stage,completed=True,model_calls=0)),flush=True)

if __name__=='__main__':main(sys.argv[1])
