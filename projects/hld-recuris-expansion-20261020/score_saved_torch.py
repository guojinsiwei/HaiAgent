"""Regrade the saved Torch submission without solver calls or changed assertions."""
from pathlib import Path
from types import SimpleNamespace
import asyncio, hashlib, json, os, subprocess, time
from verifier_setup import prepare_verifier, verifier_network, validate_test_report

R = Path(__file__).resolve().parent
A = R / "infra-repair-20261020/torch-regrade"

class Environment:
    def __init__(self, name):
        self.name = name
    async def upload_file(self, source, target):
        subprocess.run(["docker", "cp", str(source), self.name + ":" + target], check=True, capture_output=True)
    async def exec(self, command, user="root", env=None, timeout_sec=900):
        cmd = ["docker", "exec", "-u", user]
        for k, v in (env or {}).items():
            cmd += ["-e", k + "=" + str(v)]
        p = subprocess.run(cmd + [self.name, "bash", "-c", command],
            capture_output=True, text=True, timeout=timeout_sec)
        return SimpleNamespace(return_code=p.returncode, stdout=p.stdout, stderr=p.stderr)

async def main():
    A.mkdir(parents=True, exist_ok=False)
    source = next((R / "jobs/tb2hr50-09-recuris-torch-pipeline-parallelism").glob("*/submission-snapshot.json"))
    snapshot = json.loads(source.read_text())
    task = R / "dependencies/official/tasks/torch-pipeline-parallelism"
    tests = {str(f.relative_to(task / "tests")): hashlib.sha256(f.read_bytes()).hexdigest()
             for f in (task / "tests").rglob("*") if f.is_file()}
    name = "tb2hr50-torch-artifact-regrade"
    out = A / "verifier"
    out.mkdir()
    result = dict(source_trial=str(source.parent), snapshot_image=snapshot["image_id"],
        official_test_hashes=tests, paid_calls=0, timeout_seconds=900,
        cpu_limit=1, thread_limits={"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"})
    (A / "provenance.json").write_text(json.dumps(result, indent=2))
    subprocess.run(["docker", "run", "-d", "--name", name, "--label", "experiment="+R.name,
        "--network", "bridge", "--cpus", "1", "--memory", "4g", "--pids-limit", "512",
        "--user", "root", "--entrypoint", "sleep",
        "--mount", "type=bind,src="+str(task/"tests")+",dst=/tests,readonly",
        "--mount", "type=bind,src="+str(out)+",dst=/logs/verifier",
        snapshot["image_id"], "infinity"], check=True, capture_output=True)
    verifier = SimpleNamespace(task=SimpleNamespace(paths=SimpleNamespace(task_dir=task)),
        trial_paths=SimpleNamespace(verifier_dir=out), environment=Environment(name),
        verifier_env=result["thread_limits"].copy())
    try:
        with verifier_network(verifier):
            await prepare_verifier(verifier)
            started = time.time()
            try:
                p = await verifier.environment.exec("bash /tests/test.sh",
                    env=verifier.verifier_env, timeout_sec=900)
                (out / "test-stdout.txt").write_text(p.stdout)
                (out / "test-stderr.txt").write_text(p.stderr)
                validate_test_report(verifier)
                ctrf = json.loads((out / "ctrf.json").read_text())["results"]
                result.update(engineering_clean=True, reward=int((out/"reward.txt").read_text().strip()),
                    tests=ctrf["summary"], exit_code=p.return_code, elapsed=time.time()-started)
            except Exception as error:
                result.update(engineering_clean=False, error_type=type(error).__name__,
                    elapsed=time.time()-started)
    finally:
        subprocess.run(["docker", "stop", "-t", "2", name], capture_output=True)
        # Keep the original snapshot and this stopped diagnostic container.
        (A / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)

if __name__ == "__main__":
    asyncio.run(main())
