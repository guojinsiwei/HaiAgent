"""Pre-pull the official SWE-bench images for the current 50-task run only."""
from __future__ import annotations

import concurrent.futures
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time

import docker
from swebench.harness.utils import load_swebench_dataset, make_test_spec

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "image-preparation-current50"
MIN_FREE = 20 * 1024**3
WORKERS = 2
IDS = (
    "django__django-10554", "django__django-10880", "django__django-10999",
    "django__django-11138", "django__django-11749", "django__django-11951",
    "django__django-12193", "django__django-12262", "django__django-12708",
    "django__django-12741", "django__django-13023", "django__django-13033",
    "django__django-13089", "django__django-13158", "django__django-13658",
    "django__django-13809", "django__django-13933", "django__django-14053",
    "django__django-14140", "django__django-14238", "django__django-14493",
    "django__django-14534", "django__django-14752", "django__django-15098",
    "django__django-15127", "django__django-15382", "django__django-15467",
    "django__django-15957", "django__django-16819", "django__django-17084",
    "matplotlib__matplotlib-20676", "pylint-dev__pylint-4604",
    "scikit-learn__scikit-learn-13496", "scikit-learn__scikit-learn-14629",
    "scikit-learn__scikit-learn-14983", "sphinx-doc__sphinx-10435",
    "sphinx-doc__sphinx-10449", "sphinx-doc__sphinx-7757", "sphinx-doc__sphinx-7985",
    "sphinx-doc__sphinx-8056", "sphinx-doc__sphinx-8551", "sphinx-doc__sphinx-9591",
    "sphinx-doc__sphinx-9602", "sphinx-doc__sphinx-9658", "sympy__sympy-12419",
    "sympy__sympy-12481", "sympy__sympy-13757", "sympy__sympy-13798",
    "sympy__sympy-15599", "sympy__sympy-24213",
)
LOCK = threading.Lock()
STOP = threading.Event()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    source_sha = hashlib.sha256("\n".join(IDS).encode()).hexdigest()
    # Image references are fields of the current official Verified dataset.
    # Do not reconstruct names: that was valid for older SWE-bench releases only.
    dataset = load_swebench_dataset(
        "SWE-bench/SWE-bench_Verified", split="test", instance_ids=list(IDS)
    )
    by_id = {row["instance_id"]: row for row in dataset}
    if set(by_id) != set(IDS):
        missing = sorted(set(IDS) - set(by_id))
        raise ValueError(f"Current 50-task list is not contained in SWE-bench Verified: {missing}")
    states = {
        identity: {"image": make_test_spec(by_id[identity]).image, "status": "pending", "attempts": 0}
        for identity in IDS
    }
    started = now()

    def save() -> None:
        atomic_json(OUT / "status.json", {
            "started_at": started, "updated_at": now(), "pid": os.getpid(),
            "mode": "images_only_no_evaluation", "total": len(IDS),
            "instance_ids_sha256": source_sha,
            "free_gb": round(shutil.disk_usage(ROOT).free / 1024**3, 2),
            "counts": dict(Counter(row["status"] for row in states.values())),
            "tasks": states,
        })

    def set_state(identity: str, **changes: object) -> None:
        with LOCK:
            states[identity].update(changes, updated_at=now())
            save()

    def pull(identity: str) -> None:
        client = docker.from_env(timeout=180)
        image = states[identity]["image"]
        try:
            try:
                cached = client.images.get(image)
                set_state(identity, status="ready", image_id=cached.id, digests=cached.attrs.get("RepoDigests", []))
                return
            except docker.errors.ImageNotFound:
                pass
            for attempt in range(1, 6):
                if STOP.is_set() or shutil.disk_usage(ROOT).free < MIN_FREE:
                    STOP.set()
                    set_state(identity, status="paused_disk_space")
                    return
                set_state(identity, status="pulling", attempts=attempt)
                try:
                    for event in client.api.pull(image, stream=True, decode=True, platform="linux/amd64"):
                        if "error" in event:
                            raise RuntimeError(event["error"])
                    cached = client.images.get(image)
                    if cached.attrs.get("Architecture") != "amd64":
                        raise RuntimeError("Unexpected image architecture")
                    set_state(identity, status="ready", image_id=cached.id, digests=cached.attrs.get("RepoDigests", []), size=cached.attrs.get("Size"), last_error=None)
                    print(f"READY {identity}", flush=True)
                    return
                except Exception as exc:
                    set_state(identity, status="retry_wait" if attempt < 5 else "failed", last_error=str(exc)[:2000])
                    if attempt < 5:
                        time.sleep(min(10 * attempt, 40))
        finally:
            client.close()

    with (OUT / "prepare.lock").open("a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save()
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            list(pool.map(pull, IDS))
        client = docker.from_env(timeout=180)
        for identity, state in states.items():
            try:
                cached = client.images.get(state["image"])
                set_state(identity, status="ready", image_id=cached.id, digests=cached.attrs.get("RepoDigests", []))
            except docker.errors.ImageNotFound:
                if state["status"] == "ready":
                    set_state(identity, status="missing_on_final_check")
        client.close()
        atomic_json(OUT / "completion.json", {
            "finished_at": now(), "counts": dict(Counter(row["status"] for row in states.values())),
            "all_ready": all(row["status"] == "ready" for row in states.values()),
        })


if __name__ == "__main__":
    main()
