"""Cloud-only, restartable preflight; never executes a model or verifier."""
import asyncio
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
import tomllib
import urllib.request

from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths
from cloud_agent import CloudAgent, TLS_ENV

ROOT = Path('/home/ecs-user/terminalbench-paired36-20260923')
CONTROL = ROOT / 'control'
os.environ['HARBOR_TELEMETRY'] = '0'
PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({'http':'http://127.0.0.1:28761','https':'http://127.0.0.1:28761'}))
SETUP_VERSION = 'shared-python-ca-v2'


def atomic(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def fetch(url, headers=None):
    for attempt in range(3):
        try:
            # ProxyHandler mutates Request.host/tunnel state. A retry must not
            # reuse that object or CONNECT may target the proxy's own port.
            request = urllib.request.Request(url, headers=headers or {})
            with PROXY.open(request, timeout=60) as response:
                return response.read()
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(3*(attempt+1))


def resolve_image(image):
    repo, tag = image.rsplit(':', 1)
    if not repo.startswith('alexgshaw/'):
        raise ValueError('Unexpected image repository; requires audit')
    # Docker Hub is the publisher's official tag metadata API, not a mirror.
    # The pulled content is still verified against this digest by Docker.
    try:
        info = json.loads(fetch('https://hub.docker.com/v2/repositories/'+repo+'/tags/'+tag))
        digest = info.get('digest','')
        if info.get('name') == tag and re.fullmatch(r'sha256:[0-9a-f]{64}',digest):
            return repo+'@'+digest
    except (OSError,ValueError):
        pass
    token = json.loads(fetch('https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + repo + ':pull'))['token']
    data = fetch('https://registry-1.docker.io/v2/' + repo + '/manifests/' + tag,
                 {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'})
    return repo + '@sha256:' + hashlib.sha256(data).hexdigest()


async def smoke(task, pinned, index):
    directory = ROOT / 'preflight' / f"{index:02d}-{task['id'].split('/')[-1]}"
    directory.mkdir(parents=True, exist_ok=True)
    reports = []
    for method in ('bestfgs', 'raw'):
        paths = TrialPaths(trial_dir=directory / method)
        paths.trial_dir.mkdir(exist_ok=True)
        config = EnvironmentConfig.model_validate({**task['environment'], 'docker_image': pinned})
        env = DockerEnvironment(environment_dir=Path(task['task_dir'])/'environment',
                                environment_name='paired36-preflight', session_id=f'tb36-pre-{index}-{method}',
                                trial_paths=paths, task_env_config=config)
        try:
            await env.start(force_build=False)
            agent = CloudAgent(logs_dir=paths.trial_dir, model_name='deepseek-flash', method=method)
            await agent.setup(env)
            check = await env.exec("/installed-agent/python/bin/python3.12 -c \"import sys, pathlib; sys.path.insert(0,'/installed-agent/src'); import bestfgs.raw_baseline; assert not pathlib.Path('/tmp/paired-preflight-marker').exists(); pathlib.Path('/tmp/paired-preflight-marker').write_text('fresh'); print('RUNTIME_OK')\"", user='root', timeout_sec=60)
            if check.return_code != 0 or 'RUNTIME_OK' not in check.stdout:
                raise RuntimeError('Isolated runtime import/freshness check failed')
            certificates = await env.exec('/installed-agent/python/bin/python3.12 -c "import ssl; assert ssl.create_default_context().cert_store_stats()[\'x509_ca\'] > 100"',user='root',env=TLS_ENV,timeout_sec=30)
            if certificates.return_code:
                raise RuntimeError('Shared CA trust store missing')
            reports.append({'method':method, 'fresh_container':True, 'runtime_import':True, 'setup_identical':True,'ca_store':True})
        finally:
            await env.stop(delete=True)
    return reports


def main():
    lock = (CONTROL/'preparation.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = json.loads((CONTROL/'task-selection.json').read_text())
    output = CONTROL/'image-readiness.json'
    state = json.loads(output.read_text()) if output.exists() else {'selection_sha256':plan['selection_sha256'],'tasks':{},'completed':False}
    assert state['selection_sha256'] == plan['selection_sha256']
    preparation_order = list(enumerate(plan['tasks']))
    # A dedicated cloud preload is already downloading this 8.6 GB layer.
    # Prepare the other environments meanwhile; formal trial order stays frozen.
    preparation_order.sort(key=lambda pair: pair[1]['id'] == 'terminal-bench/mteb-leaderboard')
    for index, task in preparation_order:
        identity = task['id']
        if state['tasks'].get(identity,{}).get('ready') and state['tasks'][identity].get('setup_version') == SETUP_VERSION:
            continue
        state.update(current=identity, updated_at=time.time(), completed=False)
        atomic(output,state)
        print(f'PREPARING {index+1}/36 {identity}', flush=True)
        for attempt in range(1,4):
            try:
                record = state['tasks'].setdefault(identity,{})
                record['total_attempts'] = record.get('total_attempts', record.get('attempts',0)) + 1
                record.setdefault('attempt_history',[]).append({'started_at':time.time(),'attempt':record['total_attempts']})
                atomic(output,state)
                if shutil.disk_usage(ROOT).free < 25 * 1024**3:
                    raise RuntimeError('Disk guard: below 25 GiB free; stop without deleting unrelated images')
                record = state['tasks'].setdefault(identity,{})
                pinned = record.get('pinned_image') or resolve_image(task['environment']['docker_image'])
                record.update(pinned_image=pinned, original_image=task['environment']['docker_image'])
                atomic(output,state)
                # A digest is immutable; don't recontact the registry for a
                # fully cached image when rechecking the shared transport.
                cached = bool(record.get('image_id')) and subprocess.run(['docker','image','inspect',pinned],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0
                if not cached:
                    with (ROOT/'preflight-pulls.log').open('a') as log:
                        subprocess.run(['docker','pull',pinned], stdout=log, stderr=subprocess.STDOUT, check=True,timeout=7200)
                info = json.loads(subprocess.check_output(['docker','image','inspect',pinned]))[0]
                if pinned not in info.get('RepoDigests',[]):
                    raise RuntimeError('Official image digest mismatch')
                record.update(image_id=info['Id'], image_bytes=info['Size'])
                record['checks'] = asyncio.run(smoke(task,pinned,index))
                record.update(ready=True, attempts=attempt, finished_at=time.time(),setup_version=SETUP_VERSION)
                record['attempt_history'][-1].update(finished_at=time.time(), ready=True)
                record.pop('error_type',None)
                atomic(output,state)
                print(f'READY {index+1}/36 {identity}',flush=True)
                break
            except Exception as error:
                record['attempt_history'][-1].update(finished_at=time.time(),ready=False,error_type=type(error).__name__)
                state['tasks'].setdefault(identity,{}).update(ready=False, attempts=attempt, error_type=type(error).__name__, error_reason=str(getattr(error,'reason',''))[:200])
                atomic(output,state)
                print(f'PREFLIGHT_RETRY {identity} {attempt}/3 {type(error).__name__}',flush=True)
                if attempt == 3:
                    raise RuntimeError(f'Preparation stopped at {identity}; no task silently replaced') from None
                time.sleep(5*attempt)
    state.update(completed=True, current=None, updated_at=time.time(), model_calls=0, verifier_runs=0)
    atomic(output,state)
    print('ALL_36_ENVIRONMENTS_READY; NO_MODEL_CALLS',flush=True)


if __name__ == '__main__':
    main()
