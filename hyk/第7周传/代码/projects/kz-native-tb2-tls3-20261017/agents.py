import json,os
from pathlib import Path
from host_agent import PairAgent
ROOT=Path(__file__).resolve().parent

class Native(PairAgent):
    arm='native-kz'
    @staticmethod
    def name():return 'native-kz-tb2'
    async def install(self,env):
        await super().install(env)
        await env.upload_file(ROOT/'python-runtime.tar.gz','/installed-agent/python-runtime.tar.gz')
        result=await self.exec_as_root(env,'mkdir -p /opt/kz-python && tar -xzf /installed-agent/python-runtime.tar.gz --strip-components=1 -C /opt/kz-python',timeout_sec=180)
        if result.return_code:raise RuntimeError('Python runtime installation failed')
        await env.upload_file(ROOT/'native-runtime.tar.gz','/installed-agent/native-runtime.tar.gz')
        result=await self.exec_as_root(env,'tar -xzf /installed-agent/native-runtime.tar.gz -C /opt',timeout_sec=180)
        if result.return_code:raise RuntimeError('Native runtime installation failed')
        from connection_probe import probe
        await probe(self,env)
    async def execute(self,environment,payload):
        cmd=['exec','-T','-w',self.cwd]
        if environment.default_user is not None:cmd+=['-u',str(environment.default_user)]
        return await environment._run_docker_compose_command(cmd+['main','/opt/node/bin/node','/opt/kz-standalone/standalone-run.mjs'],stdin_data=json.dumps(payload).encode(),check=False,timeout_sec=None)
    async def run(self,instruction,environment,context):
        services=await environment._run_docker_compose_command(['config','--services'],check=True,timeout_sec=30)
        payload=dict(key=os.environ['TAOTOKEN_API_KEY'],task=os.environ['PAIRED_TASK'],instruction=instruction,
            proxy=os.environ['PAIRED_PROXY_URL'],no_proxy=','.join(['localhost','127.0.0.1','::1']+(services.stdout or '').splitlines()),
            spending={k:v for k,v in os.environ.items() if k.startswith('CAMPAIGN_BUDGET_')},attempt_id=os.environ['PAIRED_ATTEMPT_ID'])
        result=await self.execute(environment,payload)
        context.metadata=dict(arm=self.arm,agent_return_code=result.return_code)
        (self.logs_dir/'transport-result.json').write_text(json.dumps(context.metadata))

class OfflineNative(Native):
    @staticmethod
    def name():return 'native-kz-offline'
    async def run(self,instruction,environment,context):
        result=await self.exec_as_agent(environment,'export PATH=/opt/kz-python/bin:$PATH; /opt/kz-python/bin/python3 /opt/kz-standalone/fixture.py && /opt/kz-python/bin/python3 /opt/kz-standalone/test_native_repair.py',cwd=self.cwd,timeout_sec=150)
        if result.return_code:raise RuntimeError('Native scripted loop fixture failed')
        context.metadata=dict(paid_calls=0,original_native_loop=True)

class OfflineTimeout(OfflineNative):
    @staticmethod
    def name():return 'native-kz-offline-timeout'
    async def run(self,instruction,environment,context):
        await super().run(instruction,environment,context)
        result=await self.execute(environment,dict(offline=True,attempt_id=os.environ['PAIRED_ATTEMPT_ID']))
        if result.return_code==0:raise RuntimeError('Forced timeout failed to stop solver')
        context.metadata=dict(paid_calls=0,forced_timeout=True)
