"""Both algorithms use the same official environment and bounded continuation protocol."""
import asyncio,json,os,secrets,tempfile,threading,time,subprocess,uuid
from types import SimpleNamespace
from pathlib import Path
from host_agent import PairAgent
ROOT=Path(__file__).resolve().parent

class LHTBAgent(PairAgent):
    arm='hld-new'
    @staticmethod
    def name():return 'hld-v8-lhtb'
    def populate_context_post_run(self,context):
        try:usage=json.loads((self.logs_dir/'live/shared-state.json').read_text())
        except (FileNotFoundError,ValueError):return
        if context.metadata is None:context.metadata={}
        context.metadata['all_role_usage']=usage
        for field,value in [('n_input_tokens',usage.get('inputTokens',0)+usage.get('cacheReadTokens',0)),('n_output_tokens',usage.get('outputTokens',0)),('n_cache_tokens',usage.get('cacheReadTokens',0))]:
            if field in type(context).model_fields:setattr(context,field,value)
    async def install(self,environment):
        await super().install(environment)
        ids=await environment._run_docker_compose_command(['ps','-q'],check=True,timeout_sec=30)
        containers=[]
        for ident in (ids.stdout or '').splitlines():
            doc=json.loads(subprocess.check_output(['docker','inspect',ident],text=True))[0]
            project=doc['Config']['Labels'].get('com.docker.compose.project');assert project
            containers.append(dict(id=doc['Id'],name=doc['Name'],project=project))
        assert containers
        main=await environment._run_docker_compose_command(['ps','-q','main'],check=True,timeout_sec=30)
        self.container=main.stdout.strip();assert self.container
        self.network='lhtb24-internal-'+uuid.uuid4().hex[:12]
        subprocess.run(['docker','network','create','--internal','--label','experiment='+ROOT.name,self.network],capture_output=True,check=True)
        # The official environment starts with network_mode=none. Add an internal bridge
        # for the model-only host proxy; this creates no internet egress for the solver.
        subprocess.run(['docker','network','disconnect','none',self.container],capture_output=True,check=False)
        subprocess.run(['docker','network','connect',self.network,self.container],capture_output=True,check=True)
        doc=json.loads(subprocess.check_output(['docker','network','inspect',self.network],text=True))[0]
        self.gateway=doc['IPAM']['Config'][0]['Gateway']
        from spending import BudgetService
        from campaign import ModelProxy
        from http.server import ThreadingHTTPServer
        self.local_budget=BudgetService(ROOT,host=self.gateway,port=0)
        self.local_budget.url=f'http://{self.gateway}:{self.local_budget.server.server_port}'
        self.local_proxy=ThreadingHTTPServer((self.gateway,0),ModelProxy);self.local_proxy.daemon_threads=True
        threading.Thread(target=self.local_proxy.serve_forever,daemon=True).start()
        (self.logs_dir.parent/'operator-container.json').write_text(json.dumps(dict(containers=containers,network=self.network,gateway=self.gateway),indent=2))
    async def invoke(self,payload,timeout=None):
        cmd=['docker','exec','-i','-w',self.cwd]
        # Match the task's original identity, recorded during the official install.
        user=getattr(self,'task_user',None)
        if user is not None:cmd+=['-u',str(user)]
        cmd += [self.container,'/opt/node/bin/node','/opt/kz/container-run.mjs']
        process=await asyncio.create_subprocess_exec(*cmd,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        try:
            output,_=await asyncio.wait_for(process.communicate(json.dumps(payload).encode()),timeout=timeout)
        except (asyncio.TimeoutError,asyncio.CancelledError):
            process.terminate()
            try:await asyncio.wait_for(process.wait(),timeout=5)
            except asyncio.TimeoutError:process.kill();await process.wait()
            raise
        return SimpleNamespace(return_code=process.returncode,stdout=output.decode(errors='replace').replace(payload['key'],'[REDACTED]'))
    async def run(self,instruction,environment,context):
        phase=getattr(self,'phase',0);self.phase=phase+1
        if not hasattr(self,'deadline'):self.deadline=time.monotonic()+10800
        remaining=max(1,int(self.deadline-time.monotonic()))
        key=os.environ.get('TAOTOKEN_API_KEY','');assert key
        self.task_user=environment.default_user
        services=await environment._run_docker_compose_command(['config','--services'],check=True,timeout_sec=30)
        payload=dict(key=key,arm=self.arm,instruction=instruction,phase=phase,remaining_seconds=remaining,
            proxy=f'http://{self.gateway}:{self.local_proxy.server_port}',no_proxy=','.join(['localhost','127.0.0.1','::1',self.gateway]+(services.stdout or '').splitlines()),
            attempt_id=os.environ['PAIRED_ATTEMPT_ID'],spending={**{k:v for k,v in os.environ.items() if k.startswith('CAMPAIGN_BUDGET_')},'CAMPAIGN_BUDGET_URL':self.local_budget.url,'CAMPAIGN_BUDGET_TOKEN':self.local_budget.token})
        result=await self.invoke(payload)
        live=self.logs_dir/'live'
        def read(name):
            try:return json.loads((live/name).read_text())
            except (FileNotFoundError,ValueError):return {}
        budget=read('budget-stop.json');limit=read('limit-stop.json');provider=read('provider-stop.json')
        reason=budget.get('reason') or limit.get('reason') or ('provider_stop' if provider else None)
        if time.monotonic()>=self.deadline:reason='solver_wall_limit'
        context.metadata=dict(arm=self.arm,phase=phase,agent_return_code=result.return_code,termination_reason=reason,
            shared_usage=read('shared-state.json'),all_roles_in_budget=True,verifier_feedback_mode='binary')
        (self.logs_dir/f'phase-{phase:04d}-receipt.json').write_text(json.dumps(context.metadata,indent=2))

class HLD(LHTBAgent):pass
class Recuris(LHTBAgent):
    arm='recuris'
    @staticmethod
    def name():return 'recuris-lhtb'

class OfflineHLD(HLD):
    @staticmethod
    def name():return 'lhtb-keyless-hld'
    async def run(self,instruction,environment,context):
        count=getattr(self,'offline_phase',0);self.offline_phase=count+1
        if count and os.environ.get('ENTRY_CONTINUATION_TEST')=='1':
            check=await self.exec_as_root(environment,'test ! -e /tests && test -z "$(find /logs/verifier -mindepth 1 -maxdepth 1 -print -quit)"',timeout_sec=30)
            assert check.return_code==0,'Hidden verifier artifacts survived into continuation'
            context.metadata=dict(offline_acceptance=True,paid_calls=0,continuation_isolation_verified=True,termination_reason='per_task_budget_exhausted')
            return
        checks=await self.exec_as_agent(environment,'/opt/node/bin/node --check /opt/kz/container-run.mjs && /opt/kz-python/bin/python3 --version',cwd=self.cwd,timeout_sec=30)
        assert checks.return_code==0,'Runtime not installed'
        if os.environ.get('ENTRY_ACCEPTANCE')=='1':
            from spending import Ledger,server_for
            profile=json.loads((ROOT/'budget-profile.json').read_text());profile.update(campaign_limit_microcny=1,task_limit_microcny=1,jobs=['entry-test'])
            with tempfile.TemporaryDirectory(dir=ROOT,prefix='entry-gate-') as directory:
                ledger=Ledger(Path(directory)/'probe.sqlite',profile);token=secrets.token_urlsafe(32)
                server=server_for(ledger,token,host=self.gateway,port=0)
                threading.Thread(target=server.serve_forever,daemon=True).start()
                payload=dict(key='offline-never-transmitted',arm=self.arm,instruction=instruction,phase=0,remaining_seconds=90,
                    proxy='http://127.0.0.1:1',no_proxy=self.gateway+',localhost,127.0.0.1',attempt_id=os.environ['PAIRED_ATTEMPT_ID'],
                    spending=dict(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=f'http://{self.gateway}:{server.server_port}',CAMPAIGN_BUDGET_TOKEN=token,CAMPAIGN_BUDGET_JOB='entry-test',CAMPAIGN_BUDGET_ARM='dsh' if self.arm=='recuris' else 'kz'))
                self.task_user=environment.default_user
                try:
                    await self.invoke(payload,timeout=120)
                    stop=await self.exec_as_root(environment,'cat /logs/agent/live/budget-stop.json',timeout_sec=15)
                    assert stop.return_code==0 and json.loads(stop.stdout)['reason']=='per_task_budget_exhausted',stop.stdout
                    assert ledger.status()['settled_microcny']==ledger.status()['reserved_microcny']==0
                finally:server.shutdown();server.server_close()
        context.metadata=dict(offline_acceptance=True,paid_calls=0)
class OfflineRecuris(OfflineHLD):
    arm='recuris'
    @staticmethod
    def name():return 'lhtb-keyless-recuris'
