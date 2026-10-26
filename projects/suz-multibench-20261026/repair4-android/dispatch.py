"""Finite deployment pipeline, no GPT jobs or scheduled wakeups."""
import argparse,json,subprocess,sys,time
from pathlib import Path
import docker
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('benchmark',choices=['webarena','androidworld']);a=p.parse_args()
out=ROOT/('dispatch-'+a.benchmark+'.json');client=docker.from_env(timeout=30)
images=['suz-android-ready:20261026'] if a.benchmark=='androidworld' else ['suz-web-ready:20261026',*['docker.1ms.run/am1n3e/webarena-verified-'+s+':latest' for s in ['reddit','shopping']]]
def state(stage,**kwargs):
    value={'benchmark':a.benchmark,'stage':stage,'updated':time.time(),**kwargs}
    out.write_text(json.dumps(value,indent=2));print(json.dumps(value),flush=True)
state('waiting_for_verified_images',deadline=time.time()+7200)
for _ in range(720):
    try:
        for image in images:client.images.get(image)
        break
    except docker.errors.ImageNotFound:time.sleep(10)
else:
    state('held',reason='Image provisioning did not finish in two hours')
    raise SystemExit(1)
for phase in ['preflight','run']:
    state(phase)
    log=ROOT/'logs'/(a.benchmark+'-'+phase+'-'+str(time.time_ns())+'.log')
    with log.open('x') as f:
        process=subprocess.Popen([sys.executable,'-u',str(ROOT/'launch.py'),phase,a.benchmark,'--concurrency',('4' if phase=='preflight' else '2')],stdout=f,stderr=f,cwd=ROOT)
        try:code=process.wait(timeout=7200 if phase=='preflight' else 90000)
        except subprocess.TimeoutExpired:
            # Leave active trial containers intact for recovery; do not auto-replay.
            process.terminate();state('held',reason=phase+' pipeline watchdog timeout');raise SystemExit(1)
    if code:
        state('held',reason=phase+' failed; inspect '+str(log));raise SystemExit(code)
state('finished')
