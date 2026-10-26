"""Official artifact-only regrade; no agent execution and no API key."""
import asyncio,hashlib,json,types
from pathlib import Path
from harbor.trial.trial import Trial
from harbor.models.trial.config import TrialConfig
from harbor.environments.docker.docker import DockerEnvironment
from harbor.trial.artifact_handler import ArtifactHandler
from lifecycle_guard import install,record
R=Path(__file__).resolve().parent

def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

async def main():
    source=next((R/'jobs/tb4-01-hld-payments-pipeline-fix').glob('payments*/config.json')).parent
    before=hashes(source/'artifacts')
    config=json.loads((source/'config.json').read_text())
    config.update(trial_name='hld-payments-regrade-v1',trials_dir=str(R/'repair-v1/regrades'),source_trial={'action':'regrade','type':'local','path':str(source)})
    install(Trial,DockerEnvironment,ArtifactHandler)
    trial=await Trial.create(TrialConfig.model_validate(config))
    prepare=trial._prepare
    async def checked_prepare(self):
        record(self,'collecting',source='official_regrade')
        await prepare() # Official validation of manifest, declared inputs and copy.
        if hashes(self.paths.artifacts_dir)!=before:raise RuntimeError('Recorded artifact bytes changed during regrade')
        record(self,'artifacts_collected',source='official_regrade',source_trial=str(source))
    trial._prepare=types.MethodType(checked_prepare,trial)
    result=await trial.run()
    if hashes(source/'artifacts')!=before:raise RuntimeError('Source artifacts were modified')
    receipt=dict(source=str(source),trial=str(trial.paths.trial_dir),paid_calls=0,artifacts_sha256=before,
        verifier_result=result.verifier_result.model_dump() if result.verifier_result else None,
        exception_type=result.exception_info.exception_type if result.exception_info else None)
    (R/'repair-v1/regrade.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt),flush=True)
if __name__=='__main__':asyncio.run(main())
