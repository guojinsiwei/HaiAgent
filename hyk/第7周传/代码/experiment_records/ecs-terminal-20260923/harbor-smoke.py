"""Exercise official Harbor container API; not a benchmark result or model run."""
import asyncio
import json
from pathlib import Path
import tempfile

from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths

IMAGE = "alexgshaw/regex-log@sha256:90101b2e815323a8da20528a1439bebc407eb9761c9c68a3d557730856c878e9"
ROOT = Path("/home/ecs-user/terminalbench-setup-20260923")

async def main():
    work = Path(tempfile.mkdtemp(prefix="harbor-smoke-", dir=ROOT))
    definition = work / "environment"
    definition.mkdir()
    results = []
    for index in range(2):
        paths = TrialPaths(trial_dir=work / f"trial-{index}")
        paths.trial_dir.mkdir()
        env = DockerEnvironment(
            environment_dir=definition,
            environment_name="ecs-infrastructure-smoke",
            session_id=f"ecs-smoke-{work.name[-8:]}-{index}",
            trial_paths=paths,
            task_env_config=EnvironmentConfig(docker_image=IMAGE, cpus=1, memory_mb=512),
        )
        try:
            await env.start(force_build=False)
            result = await env.exec("test ! -e /tmp/smoke-marker && echo fresh > /tmp/smoke-marker", timeout_sec=20)
            assert result.return_code == 0, result
            source = work / f"input-{index}.txt"
            source.write_text("harbor-file-roundtrip\n")
            await env.upload_file(source, "/tmp/roundtrip.txt")
            result = await env.exec("cat /tmp/roundtrip.txt", timeout_sec=20)
            assert result.return_code == 0 and "harbor-file-roundtrip" in result.stdout, result
            received = work / f"output-{index}.txt"
            await env.download_file("/tmp/roundtrip.txt", received)
            assert received.read_text() == source.read_text()
            results.append({"fresh_environment": True, "exec": True, "upload_download": True})
        finally:
            await env.stop(delete=True)
    report = {"scope": "infrastructure_only", "image": IMAGE, "model_calls": 0, "rounds": results, "passed": True}
    (ROOT / "harbor-smoke-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))

if __name__ == "__main__":
    asyncio.run(main())
