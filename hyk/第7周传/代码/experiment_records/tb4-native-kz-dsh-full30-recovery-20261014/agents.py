"""Reuse frozen DSH and native KZ; only isolate deployment and deadline plumbing."""
import json,os
from pathlib import Path
from host_agent import PairAgent
ROOT=Path(__file__).resolve().parent
REPAIR=Path('/mnt/sdb/home/lizh639/tb4-kz-native-repair1-20261014')

class DSH(PairAgent):
    @staticmethod
    def name():return 'native-dsh-recovery'
    async def install(self,env):
        await super().install(env)
        for name in ('container-run.mjs','deadline.mjs'):
            await env.upload_file(ROOT/name,'/installed-agent/'+name)
            result=await self.exec_as_root(env,f'cp /installed-agent/{name} /opt/kz/{name}',timeout_sec=30)
            if result.return_code:raise RuntimeError('DSH deadline installation failed')

class OfflineDSH(DSH):
    @staticmethod
    def name():return 'dsh-offline-recovery'
    async def run(self,instruction,environment,context):
        result=await self.exec_as_agent(environment,'/opt/node/bin/node --check /opt/kz/container-run.mjs',cwd=self.cwd,timeout_sec=30)
        if result.return_code:raise RuntimeError('DSH wrapper syntax invalid')
        context.metadata=dict(paid_calls=0,install_ok=True)

class Native(PairAgent):
    @staticmethod
    def name():return 'native-kz-repair1-recovery'
    async def install(self,env):
        await super().install(env)
        await env.upload_file(REPAIR/'legacy-runtime.tar.gz','/installed-agent/legacy-runtime.tar.gz')
        result=await self.exec_as_root(env,'tar -xzf /installed-agent/legacy-runtime.tar.gz -C /opt',timeout_sec=180)
        if result.return_code:raise RuntimeError('Native runtime extraction failed')
    async def run(self,instruction,environment,context):
        services=await environment._run_docker_compose_command(['config','--services'],check=True,timeout_sec=30)
        payload=dict(key=os.environ['TAOTOKEN_API_KEY'],task=os.environ['PAIRED_TASK'],instruction=instruction,
            proxy=os.environ['PAIRED_PROXY_URL'],no_proxy=','.join(['localhost','127.0.0.1','::1']+(services.stdout or '').splitlines()))
        cmd=['exec','-T','-w',self.cwd]
        if environment.default_user is not None:cmd+=['-u',str(environment.default_user)]
        result=await environment._run_docker_compose_command(cmd+['main','/opt/node/bin/node','/opt/kz-standalone/standalone-run.mjs'],
            stdin_data=json.dumps(payload).encode(),check=False,timeout_sec=None)
        context.metadata=dict(arm='native-kz',agent_return_code=result.return_code)
        (self.logs_dir/'transport-result.json').write_text(json.dumps(context.metadata))

class OfflineNative(Native):
    @staticmethod
    def name():return 'native-kz-offline-recovery'
    async def run(self,instruction,environment,context):
        result=await self.exec_as_agent(environment,'python3 /opt/kz-standalone/fixture.py && python3 /opt/kz-standalone/test_native_repair.py',cwd=self.cwd,timeout_sec=150)
        if result.return_code:raise RuntimeError('Native keyless fixture failed')
        context.metadata=dict(paid_calls=0,install_ok=True,fixture=result.stdout)
