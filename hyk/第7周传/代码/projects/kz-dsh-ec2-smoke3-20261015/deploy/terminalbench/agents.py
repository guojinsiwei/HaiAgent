from host_agent import KZAgent
class DSH(KZAgent):
    @staticmethod
    def name():return 'kz-dsh-evidence-control-2'
class OfflineDSH(DSH):
    @staticmethod
    def name():return 'kz-dsh-ec2-offline'
    async def run(self,instruction,environment,context):
        result=await self.exec_as_agent(environment,'/opt/node/bin/node --check /opt/kz/container-run.mjs && /opt/node/bin/node --test /opt/kz/tests/evidence-control-2.test.mjs',cwd=self.cwd,timeout_sec=120)
        if result.return_code:raise RuntimeError('Keyless candidate checks failed')
        probe=await self.exec_as_agent(environment,"/opt/node/bin/node -e 'require(\"fs\").writeFileSync(\"/logs/agent/private-offline-probe.txt\",\"offline probe\",{mode:0o600,flag:\"wx\"})'",cwd=self.cwd,timeout_sec=30)
        if probe.return_code:raise RuntimeError('Private log handoff probe failed')
        context.metadata=dict(paid_calls=0,install_ok=True)
