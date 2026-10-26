"""Finite CPU-only fresh-round launch; no GPT automation."""
import os,subprocess,json,time
from common import ROOT,verify_ready,deployment_hash
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',NVIDIA_VISIBLE_DEVICES='void',HLD_PLANNER_PROTOCOL='2')
env['PATH']=str(ROOT/'.venv/bin')+':'+env['PATH']
with (ROOT/'logs/environment-preflight.log').open('a') as log:
    result=subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'preflight-environment.py')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
if result.returncode:raise SystemExit('Environment preflight failed; no inference queue started')
verify_ready()
if (ROOT/'STOP_DISPATCH').exists():raise SystemExit('Dispatch stopped by user')
(ROOT/'logs/accepted.json').write_text(json.dumps({'at':time.time(),'deployment_sha256':deployment_hash()}))
with (ROOT/'logs/queue.log').open('a') as log:
    result=subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'launch.py')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
raise SystemExit(result.returncode)
