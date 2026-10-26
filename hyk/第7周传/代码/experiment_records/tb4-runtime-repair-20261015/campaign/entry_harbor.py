"""Keep the official lifecycle and verifier; clean only this trial's volumes."""
import sys,asyncio
from harbor.trial.trial import Trial
from harbor.environments.docker.docker import DockerEnvironment
original_timeout=Trial._compute_agent_timeout_sec
original_compose=DockerEnvironment._run_docker_compose_command

def timeout(self):
    if self.config.agent.import_path in ('agents:DSH','agents:Native'):return None
    return original_timeout(self)

async def compose(self,command,*a,**kw):
    # --no-delete already destroys the isolated container after logs/verifier are
    # collected. Also remove only its Compose project's named/anonymous volumes.
    # Never remove shared images, other projects, or host experiment artifacts.
    if command==['down']:command=['down','--volumes']
    for attempt in range(3):
        try:return await original_compose(self,command,*a,**kw)
        except RuntimeError as error:
            transient=any(s in str(error).lower() for s in ('tls handshake timeout','connection reset by peer','temporary failure in name resolution','i/o timeout'))
            if not command or command[0]!='build' or not transient or attempt==2:raise
            # Remains inside Harbor's original build deadline. No grading or
            # task execution is replayed; only an unsuccessful image build.
            await asyncio.sleep(5*2**attempt)

if __name__=='__main__':
    Trial._compute_agent_timeout_sec=timeout
    DockerEnvironment._run_docker_compose_command=compose
    from harbor.cli.main import app
    sys.exit(app())
