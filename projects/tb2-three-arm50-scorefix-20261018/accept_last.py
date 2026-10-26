import subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent;deadline=time.monotonic()+900
while not (R/'dependency-cache/mteb-retrieve/ready.json').exists():
 if time.monotonic()>deadline:raise TimeoutError('MTEB cache preparation did not finish')
 time.sleep(3)
subprocess.run([sys.executable,str(R/'accept_scoring.py'),'mteb-retrieve'],check=True)
