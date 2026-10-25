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
    subprocess.run(SSH+['mkdir '+REMOTE],check=True,timeout=60)
    files=[p for p in ROOT.iterdir() if p.suffix in ('.py','.ps1','.txt')]
    subprocess.run(['scp','-i',KEY,'-o','BatchMode=yes',*map(str,files),HOST+':'+REMOTE+'/'],check=True,timeout=120)
    subprocess.run(['scp','-r','-i',KEY,'-o','BatchMode=yes',str(ROOT/'retrac'),HOST+':'+REMOTE+'/'],check=True,timeout=120)
    subprocess.run(SSH+[f'{PYTHON} -m venv {REMOTE}/runtime'],check=True,timeout=120)
    subprocess.run(SSH+[f'{REMOTE}/runtime/bin/python -m pip install "pytest>=8" "pydantic>=2.10.5" "docker>=7.1" "pyyaml>=6" "jinja2>=3.1"'],check=True,timeout=300)
    subprocess.run(SSH+[f'{REMOTE}/runtime/bin/python -B {REMOTE}/offline_tests.py'],check=True,timeout=120)
    subprocess.run(SSH+[f'{REMOTE}/runtime/bin/python -B {REMOTE}/prepare.py'],check=True,timeout=1800)
    for name in ('protocol.json','ready.json','original-tests.json','adapter-tests.json','docker-acceptance.json','grading-acceptance.json'):
        subprocess.run(['scp','-i',KEY,'-o','BatchMode=yes',HOST+':'+REMOTE+'/'+name,str(ROOT/name)],check=True,timeout=60)

if __name__=='__main__':main()
