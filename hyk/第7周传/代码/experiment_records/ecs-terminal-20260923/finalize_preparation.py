"""Cloud-only preparation gate. Never reads a model key or starts formal trials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/ecs-user/terminalbench-paired36-20260923')
OUTPUT=ROOT/'control/preparation-final.json'
PYTHON='/home/ecs-user/terminalbench-runtime/venv/bin/python'

def record(state, **extra):
    data={'state':state,'updated_at':time.time(),'paid_model_requests':0,**extra}
    temp=OUTPUT.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2)+'\n')
    temp.replace(OUTPUT)

def main():
    deadline=time.monotonic()+8*3600
    while time.monotonic()<deadline:
        active=subprocess.run(['systemctl','is-active','--quiet','terminalbench-preflight36-20260923']).returncode==0
        if not active: break
        record('waiting_for_36_environment_checks')
        time.sleep(30)
    else: raise RuntimeError('Preparation deadline exceeded')
    state=json.loads((ROOT/'control/image-readiness.json').read_text())
    if not state.get('completed'):
        raise RuntimeError('Environment preparation stopped before all 36 were ready')
    record('final_synthetic_and_offline_validation')
    env=dict(os.environ,HARBOR_TELEMETRY='0')
    for args in [
        ['-m','unittest','test_cloud_transport','test_control','test_relay_policy'],
        ['test_harbor_job.py'],
        ['paired_control.py','freeze'],
        ['paired_control.py','validate'],
    ]:
        subprocess.run([PYTHON,*args],cwd=HERE,env=env,check=True,timeout=600)
    protocol=json.loads((ROOT/'control/protocol.json').read_text())
    record('ready_for_deepseek_key',protocol_sha256=protocol['protocol_sha256'],tasks=36,method_runs=72,
           formal_experiment_started=False)
    print('READY_FOR_DEEPSEEK_KEY; FORMAL_EXPERIMENT_NOT_STARTED',flush=True)

if __name__=='__main__':
    try: main()
    except Exception as error:
        record('needs_attention',error_type=type(error).__name__,reason=str(error)[:400])
        raise
