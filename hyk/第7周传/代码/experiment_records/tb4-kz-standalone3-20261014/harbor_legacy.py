import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014')
sys.path.insert(0,str(BASE))
from harbor_pair import PairAgent
class LegacyAgent(PairAgent):
    @staticmethod
    def name():return 'kz2-standalone-tb4'
    async def install(self,env):
        await super().install(env)
        await env.upload_file(ROOT/'legacy-runtime.tar.gz','/installed-agent/legacy-runtime.tar.gz')
        result=await self.exec_as_root(env,'tar -xzf /installed-agent/legacy-runtime.tar.gz -C /opt',timeout_sec=180)
        if result.return_code:raise RuntimeError('Legacy runtime extraction failed')
        result=await self.exec_as_agent(env,'python3 -c "import sys; sys.path.insert(0,\'/opt/kz-standalone\'); import solve; print(\'LEGACY_IMPORT_OK\')"',cwd=self.cwd,timeout_sec=60)
        if result.return_code:raise RuntimeError('Legacy import failed: '+(result.stderr or '')[-1000:])
    async def run(self,instruction,environment,context):
        services=await environment._run_docker_compose_command(['config','--services'],check=True,timeout_sec=30)
        payload=dict(key=os.environ['TAOTOKEN_API_KEY'],task=os.environ['PAIRED_TASK'],instruction=instruction,proxy=os.environ['PAIRED_PROXY_URL'],
          no_proxy=','.join(['localhost','127.0.0.1','::1']+(services.stdout or '').splitlines()))
        cmd=['exec','-T','-w',self.cwd]
        if environment.default_user is not None:cmd+=['-u',str(environment.default_user)]
        result=await environment._run_docker_compose_command(cmd+['main','/opt/node/bin/node','/opt/kz-standalone/standalone-run.mjs'],stdin_data=json.dumps(payload).encode(),check=False,timeout_sec=None)
        context.metadata=dict(arm='legacy-kz',agent_return_code=result.return_code)
        (self.logs_dir/'transport-result.json').write_text(json.dumps(context.metadata))
class OfflineLegacy(LegacyAgent):
    @staticmethod
    def name():return 'kz2-offline-install'
    async def run(self,instruction,environment,context):
        result=await self.exec_as_agent(environment,'python3 /opt/kz-standalone/fixture.py',cwd=self.cwd,timeout_sec=150)
        if result.return_code:raise RuntimeError('Legacy keyless fixture failed: '+(result.stderr or '')[-2000:])
        context.metadata={'paid_calls':0,'install_ok':True,'fixture':result.stdout}
