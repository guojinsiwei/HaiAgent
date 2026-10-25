"""Public-only academy deployment and unpaid native acceptance."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent
KEY='C:/Users/54177/.ssh/cubestudio_notebook'
HOST='lizh639@172.16.108.236'
SSH=['ssh','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15',HOST]
REMOTE='/var/tmp/lizh639-'+ROOT.name
PYTHON='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'

def main():
    subprocess.run(SSH+['mkdir '+REMOTE],stdin=subprocess.DEVNULL,check=True,timeout=60)
    files=[p for p in ROOT.iterdir() if p.suffix in ('.py','.ps1','.txt')]
    subprocess.run(['scp','-i',KEY,'-o','BatchMode=yes',*map(str,files),HOST+':'+REMOTE+'/'],check=True,timeout=120)
    subprocess.run(['scp','-r','-i',KEY,'-o','BatchMode=yes',str(ROOT/'retrac'),HOST+':'+REMOTE+'/'],check=True,timeout=120)
    subprocess.run(SSH+[f'ln -s /var/tmp/lizh639-longcli-retrac20-college-20261006/runtime {REMOTE}/runtime'],
                   stdin=subprocess.DEVNULL,check=True,timeout=60)
    subprocess.run(SSH+[f'{REMOTE}/runtime/bin/python -B {REMOTE}/offline_tests.py'],stdin=subprocess.DEVNULL,check=True,timeout=120)
    subprocess.run(SSH+[f'{REMOTE}/runtime/bin/python -B {REMOTE}/prepare.py'],stdin=subprocess.DEVNULL,check=True,timeout=1800)
    for name in ('protocol.json','ready.json','original-tests.json','adapter-tests.json','docker-acceptance.json','grading-acceptance.json'):
        subprocess.run(['scp','-i',KEY,'-o','BatchMode=yes',HOST+':'+REMOTE+'/'+name,str(ROOT/name)],check=True,timeout=60)

if __name__=='__main__':main()
