import sys
from harbor.trial.trial import Trial
from harbor.environments.docker.docker import DockerEnvironment
from harbor.trial.artifact_handler import ArtifactHandler
from lifecycle_guard import install
original=Trial._compute_agent_timeout_sec
def timeout(self):
    if (self.config.agent.import_path or self.config.agent.name) in ('agents:HLD','agents:Recuris','agents:OfflineHLD','agents:OfflineRecuris'):return None
    return original(self)
if __name__=='__main__':
    install(Trial,DockerEnvironment,ArtifactHandler)
    Trial._compute_agent_timeout_sec=timeout
    from harbor.cli.main import app
    sys.exit(app())
