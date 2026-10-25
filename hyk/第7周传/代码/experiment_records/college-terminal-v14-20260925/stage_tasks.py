"""Create immutable task copies whose only change is the transport image reference."""
from pathlib import Path
import hashlib
import json
import shutil
import tomllib
import toml

HERE = Path(__file__).resolve().parent
ROOT = HERE / "experiment"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


selection = json.loads((HERE / "task-selection.json").read_text())
ready = json.loads((HERE / "preparation.json").read_text())
if ready.get("phase") != "data_ready" or len(ready.get("images_ready", [])) != 36:
    raise RuntimeError("All 36 images must be ready")

records = []
for item in selection["tasks"]:
    name = item["id"].split("/")[-1]
    source = HERE / "datasets" / "terminal-bench-2" / name
    target = ROOT / "pinned-tasks" / name
    if sha(source / "task.toml") != item["public_config_sha256"]:
        raise RuntimeError(f"Source task changed: {name}")
    if not target.exists():
        shutil.copytree(source, target)
        config = tomllib.loads((target / "task.toml").read_text())
        config["environment"]["docker_image"] = ready["transport_refs"][item["id"]]
        (target / "task.toml").write_text(toml.dumps(config))
    original = tomllib.loads((source / "task.toml").read_text())
    pinned = tomllib.loads((target / "task.toml").read_text())
    transport = pinned["environment"]["docker_image"]
    pinned["environment"]["docker_image"] = original["environment"]["docker_image"]
    if original != pinned or transport != ready["transport_refs"][item["id"]]:
        raise RuntimeError(f"Pinned task differs beyond image transport: {name}")
    records.append({"id": item["id"], "source_task_toml_sha256": sha(source / "task.toml"),
                    "pinned_task_toml_sha256": sha(target / "task.toml"), "transport_image": transport})

(ROOT / "control").mkdir(parents=True, exist_ok=True)
(ROOT / "control" / "task-stage.json").write_text(json.dumps({"complete": True, "tasks": records}, indent=2) + "\n")
print(json.dumps({"complete": True, "tasks": len(records)}))
