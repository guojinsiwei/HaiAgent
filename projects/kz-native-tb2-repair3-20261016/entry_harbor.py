import sys
from harbor.trial.trial import Trial
from harbor.environments.docker.docker import DockerEnvironment
from harbor.trial.artifact_handler import ArtifactHandler
from lifecycle_guard import install
original=Trial._compute_agent_timeout_sec

def timeout(self):
    identity=self.config.agent.import_path or self.config.agent.name
    if identity in ('agents:Native','agents:OfflineNative','agents:OfflineTimeout'):
        return None
    return original(self)

def configure():
    install(Trial,DockerEnvironment,ArtifactHandler)
    Trial._compute_agent_timeout_sec=timeout

if __name__=='__main__':
    configure()
    from harbor.cli.main import app
    sys.exit(app())
