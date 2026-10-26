"""Bounded deletion of approved, unused, digest-addressable public image caches."""
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path("/mnt/sdb/home/lizh639")
TB = BASE / "tb2-hld-recuris50-20261020"
A = BASE / "hld-recuris-expansion-20261020/storage-cleanup-20261021-0008"
sys.path.insert(0, str(TB))
from storage import atomic_json, supervisor_lock

def run(args, timeout=90):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)

def containers():
    p = run(["docker", "ps", "-aq"])
    p.check_returncode()
    ids = p.stdout.split()
    if not ids:
        return []
    p = run(["docker", "inspect", *ids])
    p.check_returncode()
    return json.loads(p.stdout)

def main():
    with supervisor_lock(A):
        assert not (A / "results.json").exists(), "Inspect existing cleanup before retrying"
        plan = json.loads((A / "plan.json").read_text())
        files = []
        for root in (BASE / "appworld-hld-recuris70-20261020",
                     BASE / "tb2-three-arm50-scorefix-20261018",
                     BASE / "tb4-hld-recuris7-20261019", TB):
            files.extend((root / "jobs").glob("*/*/result.json"))
            files.extend((root / "jobs").glob("*/summary.json"))
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        atomic_json(A / "protected-result-hashes.json", hashes)
        atomic_json(A / "snapshot-tags-before.json", run([
            "docker", "image", "ls", "--no-trunc", "--format", "{{.Repository}}:{{.Tag}} {{.ID}}",
            "kz-score-recovery"
        ]).stdout.splitlines())
        results = []
        started = shutil.disk_usage("/var/lib/docker").free
        for selected in plan["candidates"]:
            if shutil.disk_usage("/var/lib/docker").free >= plan["target_free_gib"] * 2**30:
                break
            p = run(["docker", "image", "inspect", selected["id"]])
            if p.returncode:
                results.append(dict(id=selected["id"], state="already_absent"))
                continue
            image = json.loads(p.stdout)[0]
            refs = {x["Image"] for x in containers()}
            if image["Id"] in refs:
                results.append(dict(id=image["Id"], state="skipped_container_reference"))
                continue
            assert image["Id"] == selected["id"]
            assert set(image.get("RepoTags") or []) == set(selected["tags"])
            assert set(image.get("RepoDigests") or []) == set(selected["digests"])
            assert image["Created"] < "2026-08-01"
            assert all(tag.startswith("swerebenchv2/") for tag in selected["tags"])
            before = shutil.disk_usage("/var/lib/docker").free
            # Docker protects referenced images/layers. No force and no container pruning.
            p = run(["docker", "image", "rm", *selected["tags"]], timeout=120)
            results.append(dict(
                **selected, state="removed" if p.returncode == 0 else "retained",
                returncode=p.returncode, stdout=p.stdout, stderr=p.stderr,
                free_before=before, free_after=shutil.disk_usage("/var/lib/docker").free))
            atomic_json(A / "progress.json", dict(updated=time.time(), results=results))
            time.sleep(1)
        changed = [name for name, digest in hashes.items()
                   if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest]
        assert not changed, changed
        prior = set(json.loads((A / "snapshot-tags-before.json").read_text()))
        current = set(run([
            "docker", "image", "ls", "--no-trunc", "--format", "{{.Repository}}:{{.Tag}} {{.ID}}",
            "kz-score-recovery"
        ]).stdout.splitlines())
        assert prior <= current, "A protected historical snapshot disappeared"
        result = dict(
            completed=datetime.datetime.now().isoformat(), results=results,
            removed=sum(x["state"] == "removed" for x in results),
            free_before=started, free_after=shutil.disk_usage("/var/lib/docker").free,
            protected_results_verified=len(hashes), historical_snapshots_preserved=len(prior),
            no_container_deletion=True, no_forced_removal=True)
        atomic_json(A / "results.json", result)
        print(json.dumps({k: v for k, v in result.items() if k != "results"}), flush=True)

if __name__ == "__main__":
    main()
