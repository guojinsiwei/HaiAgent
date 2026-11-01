import json
import os
from harbor_kz import KZInstalledAgent,ROOT

class KZRetry1(KZInstalledAgent):
    async def install(self,environment):
        await super().install(environment)
        for name in ['route-audit.mjs','dsh_runtime.py','container-retry1.py']:
            await environment.upload_file(ROOT/name,'/opt/kz/'+name)
        await self.exec_as_root(environment,'python /opt/kz/offline_headless.py --wire-audit',timeout_sec=120)

    async def run(self,instruction,environment,context):
        key=os.environ.get('TAOTOKEN_API_KEY','')
        if not key: raise RuntimeError('New key required')
        prompt=self.logs_dir/'instruction.txt'
        prompt.write_text(instruction,encoding='utf-8')
        await environment.upload_file(prompt,'/opt/kz/instruction.txt')
        result=await environment._run_docker_compose_command(
            ['exec','-T','-w','/app','main','python','/opt/kz/container-retry1.py'],
            stdin_data=(key+'\n').encode(),check=False,timeout_sec=2150)
        context.metadata={'agent_return_code':result.return_code,'provider_actual':'taotoken-token-plan',
            'endpoint':'https://api.taotoken.net/token/v1/messages','retry_of':'taotoken-smoke',
            'smoke_only':True,'max_requests':40,'max_tools':80,'live_gate_max_requests':8}
        (self.logs_dir/'transport-result.json').write_text(json.dumps(context.metadata))
