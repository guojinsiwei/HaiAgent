"""Record setup evidence without inspecting credentials or evaluation answers."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import subprocess

root = Path("/home/ecs-user/terminalbench-setup-20260923")
project = Path("/home/ecs-user/BestFGS-blocking-memory-v12")
packages = sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions() if d.metadata.get("Name"))
(root / "runtime-packages.lock.txt").write_text("\n".join(f"{name}=={version}" for name, version in packages) + "\n")
hashes = {str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(project.rglob("*.py")) if "__pycache__" not in path.parts}
(root / "deployed-source-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
report = {
    "python": platform.python_version(),
    "harbor": importlib.metadata.version("harbor"),
    "docker": subprocess.check_output(["docker", "version", "--format", "{{.Server.Version}}"], text=True).strip(),
    "compose": subprocess.check_output(["docker", "compose", "version", "--short"], text=True).strip(),
    "harbor_smoke": json.loads((root / "harbor-smoke-result.json").read_text()),
    "formal_trials_started": False,
    "model_credentials_configured_by_this_setup": False,
    "deployed_python_files": len(hashes),
}
(root / "environment-validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
