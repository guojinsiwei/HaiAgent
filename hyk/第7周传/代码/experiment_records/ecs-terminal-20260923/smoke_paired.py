import asyncio
import json
import os
from pathlib import Path
import tempfile

from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths
from cloud_agent import CloudAgent

HERE = Path(__file__).resolve().parent
os.environ['HARBOR_TELEMETRY']='0'

async def main():
    root = Path(tempfile.mkdtemp(prefix='paired-synthetic-',dir=HERE))
    definition = root/'environment'
    definition.mkdir()
    reports=[]
    for method in ('bestfgs','raw'):
        paths=TrialPaths(trial_dir=root/method)
        paths.trial_dir.mkdir()
        env=DockerEnvironment(environment_dir=definition,environment_name='paired-synthetic',
            session_id=f'paired-synthetic-{root.name[-6:]}-{method}',trial_paths=paths,
            task_env_config=EnvironmentConfig(docker_image='alexgshaw/regex-log@sha256:90101b2e815323a8da20528a1439bebc407eb9761c9c68a3d557730856c878e9',cpus=1,memory_mb=2048))
        try:
            await env.start(force_build=False)
            await CloudAgent(logs_dir=paths.trial_dir,model_name='fixture',method=method).setup(env)
            await env.upload_file(HERE/'fixture_agent.py','/installed-agent/fixture_agent.py')
            result=await env.exec(f'PYTHONPATH=/installed-agent/src /installed-agent/python/bin/python3.12 /installed-agent/fixture_agent.py {method}',env={'DEEPSEEK_API_KEY':'fixture-unused'},user='root',timeout_sec=60)
            if result.return_code:
                raise RuntimeError(f'Synthetic {method} failed: {result.stderr[-2500:]}')
            reports.append(json.loads(result.stdout))
        finally:
            await env.stop(delete=True)
    (HERE/'paired-smoke-result.json').write_text(json.dumps({'passed':True,'scope':'synthetic_not_benchmark','api_requests':0,'methods':reports},indent=2))
    print(json.dumps(reports))

asyncio.run(main())
