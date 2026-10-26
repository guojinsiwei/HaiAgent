from host_agent import KZAgent,PairAgent
class PureDSH(PairAgent):
    @staticmethod
    def name():return 'pure-dsh-tb2-paired'
class DSH(KZAgent):
    @staticmethod
    def name():return 'kz-dsh-evidence-control-3'
class OfflineDSH(DSH):
    @staticmethod
    def name():return 'kz-dsh-ec3-offline'
    async def run(self,instruction,environment,context):
        result=await self.exec_as_agent(environment,'/opt/node/bin/node --check /opt/kz/container-run.mjs && /opt/node/bin/node --test /opt/kz/tests/evidence-control-2.test.mjs /opt/kz/tests/review-policy.test.mjs',cwd=self.cwd,timeout_sec=120)
        if result.return_code:raise RuntimeError('Keyless candidate checks failed')
        probe=await self.exec_as_agent(environment,"/opt/node/bin/node -e 'require(\"fs\").writeFileSync(\"/logs/agent/private-offline-probe.txt\",\"offline probe\",{mode:0o600,flag:\"wx\"})'",cwd=self.cwd,timeout_sec=30)
        if probe.return_code:raise RuntimeError('Private log handoff probe failed')
        context.metadata=dict(paid_calls=0,install_ok=True)

class OfflinePureDSH(OfflineDSH):
    arm='dsh'
    @staticmethod
    def name():return 'pure-dsh-offline'

class OfflineTimeout(OfflineDSH):
    @staticmethod
    def name():return 'paired-forced-timeout-offline'
    async def run(self,instruction,environment,context):
        await super().run(instruction,environment,context)
        import os,json,shlex
        script="""import fs from 'node:fs';import {spawn} from 'node:child_process';import {deadline} from '/opt/kz/deadline.mjs';
const child=spawn('/opt/node/bin/node',['-e','setInterval(()=>{},1000)'],{detached:true,stdio:'ignore'});
const guard=deadline(child,0.2,()=>{});
const result=await new Promise(r=>child.on('exit',(code,signal)=>r({code,signal})));
fs.writeFileSync('/logs/agent/offline-timeout.json',JSON.stringify({...result,timed_out:guard.reason==='solver_wall_limit'}));guard.finish();
"""
        result=await self.exec_as_agent(environment,'/opt/node/bin/node --input-type=module -e '+shlex.quote(script),cwd=self.cwd,timeout_sec=30)
        if result.return_code:raise RuntimeError('Offline timeout probe failed')
