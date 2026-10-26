"""Prepare a fresh, one-task DH arm without changing earlier results."""
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
BASE = Path("/mnt/sdb/home/lizh639")
OLD = BASE / "longcli-resume-five-20261007/dh-resume-20261007"
EXPECTED = BASE / "longcli-dh-cow-format-repair-20261007"


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert ROOT == EXPECTED
    assert OLD.is_dir()
    previous = read(OLD / "jobs/dh--61810_cow/summary.json")
    assert previous["state"] == "engineering_failure"
    assert previous["stop_reason"] == "model_or_protocol_error_limit"
    assert not (ROOT / "protocol.json").exists(), "Already prepared; do not overwrite"
    assert not (ROOT / "jobs").exists(), "Existing results must not be overwritten"

    for source in OLD.glob("*.py"):
        target = ROOT / source.name
        assert not target.exists(), target
        shutil.copyfile(source, target)
    for name in ("compatibility", "sources", "upstream", "input-manifest.json"):
        source = (OLD / name).resolve()
        assert source.exists(), source
        (ROOT / name).symlink_to(source, target_is_directory=source.is_dir())
    for name in ("jobs", "grades", "incoming", "host-tmp", "empty-tests", "acceptance-jobs"):
        (ROOT / name).mkdir()

    protocol = read(OLD / "protocol.json")
    rows = [row for row in protocol["tasks"] if row["task"] == "61810_cow"]
    assert len(rows) == 1
    protocol.update(experiment=ROOT.name, tasks=rows, run_tasks=rows,
                    total_trials=1, concurrency=1)
    protocol["format_repair"] = {
        "scope": "memory_review.reason over 400 characters only",
        "effect": "bound non-executable explanation before existing validation",
        "unchanged": ["model", "task", "decision_logic", "action", "budget", "grader"],
    }
    save(ROOT / "protocol.json", protocol)
    save(ROOT / "resume-plan.json", {
        "method": "dh", "root": str(ROOT), "source": str(OLD),
        "concurrency": 1, "preserved": [], "run_tasks": rows,
        "previous_failure": str(OLD / "jobs/dh--61810_cow/summary.json"),
        "previous_failure_sha256": sha(OLD / "jobs/dh--61810_cow/summary.json"),
    })
    files = ("cow_format_repair.py", "cow_worker.py", "resume_worker.py",
             "repair_runtime.py", "runner.py", "protocol.json", "resume-plan.json")
    save(ROOT / "cow-ready.json", {"ready": True, "paid_model_calls": 0,
                                   "hashes": {name: sha(ROOT / name) for name in files}})
    print(json.dumps({"ready": True, "task": "61810_cow", "new_root": str(ROOT),
                      "old_result_preserved": True, "paid_model_calls": 0}))


if __name__ == "__main__":
    main()
