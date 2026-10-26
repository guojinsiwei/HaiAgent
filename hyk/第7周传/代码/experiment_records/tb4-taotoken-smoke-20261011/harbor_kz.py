"""Pinned Harbor 0.24.0 installed-agent adapter, Docker only.

Use Harbor's stdin_data transport so the real credential never enters a
serialized job config, command argument, container spec, or credential file.
"""
import json
import os
from pathlib import Path
from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.docker.docker import DockerEnvironment

ROOT = Path(__file__).resolve().parent

class KZInstalledAgent(BaseInstalledAgent):
    @staticmethod
    def name():
        return 'kz-dsh-taotoken-smoke'

    async def install(self, environment):
        if not isinstance(environment, DockerEnvironment):
            raise RuntimeError('This smoke adapter requires Harbor Docker')
        await environment.upload_file(ROOT / 'runtime.tar.gz', '/installed-agent/runtime.tar.gz')
        result = await self.exec_as_root(environment,
            'tar -xzf /installed-agent/runtime.tar.gz -C /opt && '
            'python /opt/kz/prepare_smoke.py && '
            'cd /opt/kz && /opt/node/bin/node scripts/check-host.mjs', timeout_sec=180)
        if result.return_code:
            raise RuntimeError('Runtime validation failed: ' + (result.stdout or '')[-3000:])
        await environment.upload_file(ROOT / 'offline_headless.py', '/opt/kz/offline_headless.py')
        await environment.upload_file(ROOT / 'route.patch.yml', '/opt/kz/route.patch.yml')
        await self.exec_as_root(environment, 'python /opt/kz/offline_headless.py', timeout_sec=120)

    async def run(self, instruction, environment, context):
        key = os.environ.get('TAOTOKEN_API_KEY', '')
        if not key:
            raise RuntimeError('New TaoToken key required; no credential reuse')
        prompt = self.logs_dir / 'instruction.txt'
        prompt.write_text(instruction, encoding='utf-8')
        await environment.upload_file(prompt, '/opt/kz/instruction.txt')
        result = await environment._run_docker_compose_command(
            ['exec', '-T', '-w', '/app', 'main', 'python', '/opt/kz/container-run.py'],
            stdin_data=(key + '\n').encode(), check=False, timeout_sec=1940)
        # Do not raise on agent failure: Harbor must still grade partial artifacts.
        context.metadata = {'agent_return_code': result.return_code,
                            'provider_actual': 'taotoken-token-plan',
                            'endpoint': 'https://api.taotoken.net/token/v1/messages',
                            'smoke_only': True, 'max_requests': 40, 'max_tools': 80}
        (self.logs_dir / 'transport-result.json').write_text(json.dumps(context.metadata))
