"""Same frozen DSH runtime; the KZ plugin is the only algorithm overlay."""
from pathlib import Path
from host_agent import PairAgent
ROOT=Path(__file__).resolve().parent

class DSH(PairAgent):
    @staticmethod
    def name(): return 'ctyun-dsh-firstpass'
    async def install(self, env):
        await super().install(env)
        for name in ('container-run.mjs','deadline.mjs','provider-guard.mjs','spending-client.mjs','messages-protocol.mjs','route-audit.mjs','offline-provider.mjs'):
            await env.upload_file(ROOT/name,'/installed-agent/'+name)
            result=await self.exec_as_root(env,f'cp /installed-agent/{name} /opt/kz/{name}',timeout_sec=30)
            if result.return_code: raise RuntimeError('Wrapper installation failed')

class KZDSH(DSH):
    arm='kz'
    @staticmethod
    def name(): return 'ctyun-kzdsh-firstpass'

class OfflineDSH(DSH):
    offline=True
    async def run(self,instruction,environment,context):
        import os,json
        os.environ['TAOTOKEN_API_KEY']='offline-fixture-key'
        await super().run(instruction,environment,context)
        marker=json.loads((self.logs_dir/'live/offline-transport.json').read_text())
        if marker!={'passed':True,'paid_calls':0}:raise RuntimeError('Offline runtime acceptance failed')
        context.metadata=dict(paid_calls=0,install_ok=True)

class OfflineKZDSH(OfflineDSH):
    arm='kz'
