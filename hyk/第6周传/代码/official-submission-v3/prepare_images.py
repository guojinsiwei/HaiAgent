"""Cache the fixed SWE100 official images without running any evaluation."""
import concurrent.futures
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time

import docker
from swebench.harness.test_spec.test_spec import TestSpec

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "image-preparation"
LOCK = threading.Lock()
STOP = threading.Event()
MIN_FREE = 20 * 1024**3


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def main():
    OUT.mkdir(exist_ok=True)
    with (OUT / "prepare.lock").open("a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prediction_bytes = (ROOT / "bestfgs.jsonl").read_bytes()
        ids = [r["instance_id"] for r in map(json.loads, prediction_bytes.decode("utf-8-sig").splitlines())]
        raw_ids = [r["instance_id"] for r in map(json.loads, (ROOT / "raw.jsonl").read_text(encoding="utf-8-sig").splitlines())]
        assert len(ids) == len(set(ids)) == 100 and set(ids) == set(raw_ids)
        assert all(re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+", i) for i in ids)
        # Use the installed harness's property so these are exactly its image keys.
        states = {}
        for identity in ids:
            spec = object.__new__(TestSpec)
            spec.instance_id, spec.arch = identity, "x86_64"
            spec.namespace, spec.instance_image_tag = "swebench", "latest"
            states[identity] = {"image": spec.instance_image_key, "status": "pending", "attempts": 0}
        started = now()

        def write_status():
            save_json(OUT / "status.json", {
                "started_at": started, "updated_at": now(), "pid": os.getpid(),
                "mode": "images_only_no_evaluation", "total": 100,
                "source_sha256": hashlib.sha256(prediction_bytes).hexdigest(),
                "free_gb": round(shutil.disk_usage(ROOT).free / 1024**3, 2),
                "counts": dict(Counter(v["status"] for v in states.values())),
                "tasks": states,
            })

        def change(identity, **changes):
            with LOCK:
                states[identity].update(changes, updated_at=now())
                write_status()

        def worker(identity):
            client = docker.from_env(timeout=180)
            image = states[identity]["image"]
            logfile = OUT / (identity + ".log")
            try:
                try:
                    cached = client.images.get(image)
                    change(identity, status="ready", image_id=cached.id, digests=cached.attrs.get("RepoDigests", []))
                    return
                except docker.errors.ImageNotFound:
                    pass
                for attempt in range(1, 6):
                    if STOP.is_set() or shutil.disk_usage(ROOT).free < MIN_FREE:
                        STOP.set()
                        change(identity, status="paused_disk_space")
                        return
                    change(identity, status="pulling", attempts=attempt)
                    try:
                        last_update = 0.0
                        with logfile.open("a", encoding="utf-8") as log:
                            log.write(f"\n{now()} attempt={attempt}\n")
                            for event in client.api.pull(image, stream=True, decode=True, platform="linux/amd64"):
                                if "error" in event:
                                    raise RuntimeError(event["error"])
                                if event.get("status") not in ("Downloading", "Extracting"):
                                    log.write(json.dumps(event) + "\n")
                                    log.flush()
                                if time.monotonic() - last_update > 15:
                                    change(identity, last_event=event)
                                    last_update = time.monotonic()
                        cached = client.images.get(image)
                        if cached.attrs.get("Architecture") != "amd64":
                            raise RuntimeError("Unexpected image architecture")
                        change(identity, status="ready", image_id=cached.id, digests=cached.attrs.get("RepoDigests", []), size=cached.attrs.get("Size"), last_error=None)
                        print(f"READY {identity}", flush=True)
                        return
                    except Exception as error:
                        change(identity, status="retry_wait" if attempt < 5 else "failed", last_error=str(error)[:2000])
                        print(f"RETRY {identity} attempt={attempt}: {str(error)[:200]}", flush=True)
                        if attempt < 5:
                            time.sleep(min(10 * attempt, 40))
            finally:
                client.close()

        write_status()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, i) for i in ids]
            for future in concurrent.futures.as_completed(futures):
                future.result()
        # Verify every tag still resolves locally after the entire preparation run.
        client = docker.from_env()
        for identity in ids:
            try:
                cached = client.images.get(states[identity]["image"])
                change(identity, status="ready", image_id=cached.id, digests=cached.attrs.get("RepoDigests", []))
            except docker.errors.ImageNotFound:
                if states[identity]["status"] == "ready":
                    change(identity, status="missing_on_final_check")
        client.close()
        with LOCK:
            write_status()
            save_json(OUT / "completion.json", {"finished_at": now(), "counts": dict(Counter(v["status"] for v in states.values())), "all_ready": all(v["status"] == "ready" for v in states.values())})
        print("FINISHED " + json.dumps(dict(Counter(v["status"] for v in states.values()))), flush=True)


if __name__ == "__main__":
    main()
