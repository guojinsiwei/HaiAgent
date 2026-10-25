"""Use official Harbor containers, original task user and separate verifier."""
import json,os,shlex,tempfile,asyncio,hashlib
from pathlib import Path
from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.docker.docker import DockerEnvironment
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014')

class PairAgent(BaseInstalledAgent):
    arm='dsh'
    @staticmethod
    def name():return 'dsh-paired'
    async def install(self,env):
        if not isinstance(env,DockerEnvironment):raise RuntimeError('Docker required')
        await env.upload_file(BASE/'runtime-final.tar.gz','/installed-agent/runtime.tar.gz')
        await self.exec_as_root(env,'tar -xzf /installed-agent/runtime.tar.gz -C /opt',timeout_sec=180)
        identity=await self.exec_as_agent(env,'id -u; id -g; pwd',timeout_sec=30)
        uid,gid,cwd=identity.stdout.strip().splitlines()[-3:]
        if not uid.isdigit() or not gid.isdigit() or cwd=='/':raise RuntimeError('Unusable task identity/workdir')
        self.cwd=cwd
        task=os.environ.get('PAIRED_TASK')
        if task:
            services=await env._run_docker_compose_command(['config','--services'],check=True,timeout_sec=30)
            fingerprints={};image_ids={}
            for service in (services.stdout or '').splitlines():
                images=await env._run_docker_compose_command(['images','-q',service],check=True,timeout_sec=30)
                ids=sorted(set((images.stdout or '').splitlines()));image_ids[service]=ids
                fingerprints[service]=[]
                for image_id in ids:
                    proc=await asyncio.create_subprocess_exec('docker','image','inspect',image_id,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                    out,_=await proc.communicate()
                    if proc.returncode:raise RuntimeError('Cannot attest task image')
                    doc=json.loads(out)[0];cfg=doc['Config']
                    # Compose's changing build provenance changes manifest IDs.
                    # Compare actual filesystem layers + effective image config,
                    # not the per-build attestation metadata or creation time.
                    content=dict(rootfs=doc['RootFS'],arch=doc['Architecture'],os=doc['Os'],config={k:cfg.get(k) for k in ('Cmd','Entrypoint','Env','WorkingDir','User','Volumes','ExposedPorts','Healthcheck')})
                    fingerprints[service].append(hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest())
            signature=dict(images=fingerprints,uid=uid,gid=gid,cwd=cwd)
            if not signature['images']:raise RuntimeError('No task image identity')
            (self.logs_dir/'image-check.json').write_text(json.dumps(dict(signature=signature,image_ids=image_ids)))
            locks=ROOT/'environment-locks';locks.mkdir(exist_ok=True);lock=locks/(task+'.json')
            with tempfile.NamedTemporaryFile(mode='w',dir=locks,delete=False) as f:
                json.dump(signature,f);temporary=Path(f.name)
            try:
                try:os.link(temporary,lock)
                except FileExistsError:pass
                if json.loads(lock.read_text())!=signature:raise RuntimeError('Paired image/user/workdir drift before API')
            finally:temporary.unlink()
        await self.exec_as_root(env,f'mkdir -p /logs/agent && chown {uid}:{gid} /logs/agent',timeout_sec=30)
        # Root installs packages; solver remains the original task user.
        await self.exec_as_agent(env,'/opt/node/bin/node --version && test -w /dev/null && test -w .',cwd=cwd,timeout_sec=30)
    async def run(self,instruction,environment,context):
        env=environment
        key=os.environ.get('TAOTOKEN_API_KEY','')
        if not key:raise RuntimeError('Fresh hidden key input required')
        services=await env._run_docker_compose_command(['config','--services'],check=True,timeout_sec=30)
        no_proxy=','.join(['localhost','127.0.0.1','::1']+(services.stdout or '').splitlines())
        payload=dict(key=key,arm=self.arm,instruction=instruction,proxy=os.environ['PAIRED_PROXY_URL'],no_proxy=no_proxy)
        command=['exec','-T','-w',self.cwd]
        if env.default_user is not None:command+=['-u',str(env.default_user)]
        result=await env._run_docker_compose_command(command+['main','/opt/node/bin/node','/opt/kz/container-run.mjs'],
            stdin_data=json.dumps(payload).encode(),check=False,timeout_sec=None)
        context.metadata={'arm':self.arm,'agent_return_code':result.return_code,'budget_mode':'unlimited','shared_requests':None,'shared_tools':None,'solver_seconds':None}
        (self.logs_dir/'transport-result.json').write_text(json.dumps(context.metadata))
        # Nonzero solver still gets the official partial-artifact evaluation.

class KZAgent(PairAgent):
    arm='kz'
    @staticmethod
    def name():return 'kz-dsh-paired'

class OfflineAgent(PairAgent):
    @staticmethod
    def name():return 'offline-install-verifier'
    async def run(self,instruction,environment,context):
        # Empty solver proves grading runs; never expose grader checks to solver.
        context.metadata={'offline_acceptance':True,'paid_calls':0}
