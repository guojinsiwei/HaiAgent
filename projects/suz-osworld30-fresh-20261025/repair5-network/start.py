import os,subprocess,json,time
from common import ROOT,verify_ready
os.environ.update(CUDA_VISIBLE_DEVICES='',NVIDIA_VISIBLE_DEVICES='void',HLD_PLANNER_PROTOCOL='2')
os.environ['PATH']=str(ROOT/'.venv/bin')+':'+os.environ['PATH']
for script in ['preflight-environment.py']:
 with (ROOT/'logs'/str(script+'.log')).open('a') as log:
  p=subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/script)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
 if p.returncode:raise SystemExit('Preflight failed: '+script)
verify_ready()
with (ROOT/'logs/queue.log').open('a') as log:
 raise SystemExit(subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'launch.py')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT).returncode)
