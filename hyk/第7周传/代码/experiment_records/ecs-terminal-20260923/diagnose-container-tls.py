import asyncio
import json
from pathlib import Path
import tempfile
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths
from cloud_agent import CloudAgent

async def main():
    root=Path(tempfile.mkdtemp(prefix='tls-check-',dir=Path(__file__).parent))
    env=DockerEnvironment(environment_dir=root,environment_name='tls-check',session_id='tb36-tls-check',
        trial_paths=TrialPaths(trial_dir=root),task_env_config=EnvironmentConfig(docker_image='alexgshaw/regex-log@sha256:90101b2e815323a8da20528a1439bebc407eb9761c9c68a3d557730856c878e9',cpus=1,memory_mb=2048))
    try:
        await env.start(force_build=False)
        await CloudAgent(logs_dir=root,model_name='fixture').setup(env)
        code="""import os,ssl,urllib.request,urllib.error,json
from urllib.parse import urlsplit
print('CA_DEFAULT',ssl.get_default_verify_paths())
print('PROXY_HOSTS',{k:urlsplit(v).hostname for k,v in urllib.request.getproxies().items()})
for ca in [None,'/etc/ssl/certs/ca-certificates.crt']:
 try:
  r=urllib.request.urlopen('https://api.deepseek.com/models',context=ssl.create_default_context(cafile=ca),timeout=20)
  print(ca,r.status)
 except Exception as e: print(ca,type(e).__name__,getattr(e,'code',None),str(e)[:300])
"""
        import shlex
        result=await env.exec('/installed-agent/python/bin/python3.12 -c '+shlex.quote(code),user='root',timeout_sec=55)
        print(result.stdout)
    finally: await env.stop(delete=True)
asyncio.run(main())
