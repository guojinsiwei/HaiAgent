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

