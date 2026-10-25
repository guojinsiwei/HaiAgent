"""Deploy only public source and offline fixtures; no credentials."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
KEY='C:/Users/54177/.ssh/cubestudio_notebook'
COLLEGE=['ssh','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15','lizh639@172.16.108.236']
REMOTE='/mnt/lizh639/'+ROOT.name
PROXY='ProxyCommand=ssh -i '+KEY+' -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p lizh639@172.16.108.236'
PYTHON='/mnt/lizh639/envs/swe-eval/bin/python'

def cube(worker):
    return ['ssh','-i',KEY,'-p',str((31081,31121)[worker]),'-o','BatchMode=yes','-o','ConnectTimeout=15','-o',PROXY,'root@172.16.108.241']

def main(worker):
    if worker==0:
        subprocess.run(cube(worker)+['mkdir '+REMOTE],check=True,timeout=30)
        files=[p for p in ROOT.iterdir() if p.suffix in ('.py','.txt','.ps1')]
        subprocess.run(['scp','-i',KEY,'-P','31081','-o','BatchMode=yes','-o',PROXY,
            *map(str,files),'root@172.16.108.241:'+REMOTE+'/'],check=True,timeout=120)
        subprocess.run(['scp','-r','-i',KEY,'-P','31081','-o','BatchMode=yes','-o',PROXY,
            str(ROOT/'retrac'),'root@172.16.108.241:'+REMOTE+'/'],check=True,timeout=120)
        subprocess.run(cube(worker)+[f'{PYTHON} -m venv {REMOTE}/test-env'],check=True,timeout=120)
        subprocess.run(cube(worker)+[f'{REMOTE}/test-env/bin/python -m pip install "pytest>=8" "pydantic>=2.10.5"'],check=True,timeout=300)
        subprocess.run(cube(worker)+[f'{REMOTE}/test-env/bin/python -B {REMOTE}/offline_tests.py'],check=True,timeout=120)
    result=subprocess.run(cube(worker)+[f'{PYTHON} -B {REMOTE}/prepare.py --worker {worker}'],timeout=1800)
    assert result.returncode==0,'Offline acceptance failed; no paid launch'
    for name in (f'acceptance-{worker}-r1.json','protocol.json',f'ready-{worker}.json','original-tests.json','adapter-tests.json'):
        subprocess.run(['scp','-i',KEY,'-P',str((31081,31121)[worker]),'-o','BatchMode=yes','-o',PROXY,
            'root@172.16.108.241:'+REMOTE+'/'+name,str(ROOT/name)],check=True,timeout=60)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=int,required=True);main(p.parse_args().worker)
