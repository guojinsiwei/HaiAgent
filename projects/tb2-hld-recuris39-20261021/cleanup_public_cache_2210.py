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
TB = BASE / "tb2-hld-recuris39-20261021"
A = TB / "storage-cleanup-20261021-2210"
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
        files = list(BASE.glob("*/jobs/*/*/result.json")) + list(BASE.glob("*/jobs/*/summary.json"))
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        atomic_json(A / "protected-result-hashes.json", hashes)
        atomic_json(A / "snapshot-tags-before.json", run([
            "docker", "image", "ls", "--no-trunc", "--format", "{{.Repository}}:{{.Tag}} {{.ID}}",
            "kz-score-recovery"
        ]).stdout.splitlines())
        results = []
        started = shutil.disk_usage("/var/lib/docker").free
        for offset in range(0, len(plan["candidates"]), 40):
            if shutil.disk_usage("/var/lib/docker").free >= plan["target_free_gib"] * 2**30:
                break
            selected_batch = plan["candidates"][offset:offset+40]
            live = run(["docker", "image", "inspect", *[x["id"] for x in selected_batch]], timeout=120)
            if live.returncode:
                raise RuntimeError("Image inventory changed; inspect before continuing")
            docs = {x["Id"]: x for x in json.loads(live.stdout)}
            refs = {x["Image"] for x in containers()}
            tags=[];approved=[]
            for selected in selected_batch:
                image=docs[selected["id"]]
                if image["Id"] in refs:
                    results.append(dict(id=image["Id"],state="skipped_container_reference"));continue
                assert set(image.get("RepoTags") or []) == set(selected["tags"])
                assert set(image.get("RepoDigests") or []) == set(selected["digests"])
                assert image["Created"] < "2026-08-01"
                assert selected["tags"] and all(t.startswith("swerebenchv2/") for t in selected["tags"])
                tags.extend(selected["tags"]);approved.append(selected)
            if not tags:continue
            before=shutil.disk_usage("/var/lib/docker").free
            p=run(["docker","image","rm",*tags],timeout=180)
            atomic_json(A/f"batch-{offset:04d}.json",dict(selected=approved,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
            remaining=set(run(["docker","image","ls","--no-trunc","-q"]).stdout.split())
            for selected in approved:
                results.append(dict(**selected,state="removed" if selected["id"] not in remaining else "retained"))
            atomic_json(A/"progress.json",dict(updated=time.time(),results=results,free_gib=shutil.disk_usage("/var/lib/docker").free/2**30))
            print(json.dumps(dict(batch=offset,removed=sum(x["state"]=="removed" for x in results),free_gib=shutil.disk_usage("/var/lib/docker").free/2**30)),flush=True)
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
