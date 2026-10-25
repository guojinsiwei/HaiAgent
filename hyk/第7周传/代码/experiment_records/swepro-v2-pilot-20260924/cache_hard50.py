#!/usr/bin/env python3
"""Cache one immutable half of the frozen SWE-bench Pro HARD-50 selection."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path("/mnt/lizh639/bestfgs-runs/swepro-v2-hard50-v13-20260924")
EXPECTED = "381f9e131112c2779c61ad24afc678755b3c0147ef050ca4c328d301defeb7fd"
HOSTS = ("lizh639-aa91", "lizh639-8e64")


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124)


def run_capture(command: list[str], *, timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(command, 124, error.stdout or b"", error.stderr or b"")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, choices=(0, 1), required=True)
    args = parser.parse_args()
    if os.uname().nodename != HOSTS[args.index]:
        raise SystemExit("cache worker launched on the wrong CubeStudio container")
    selection = ROOT / "control/hard50_ids.txt"
    if hashlib.sha256(selection.read_bytes()).hexdigest() != EXPECTED:
        raise SystemExit("frozen selection hash mismatch")
    ids = [line.strip() for line in selection.read_text().splitlines() if line.strip()]
    ordered = sorted(ids, key=lambda value: (hashlib.sha256(value.encode()).hexdigest(), value))
    assigned = ordered[args.index::2]
    lock_path = ROOT / f"image-cache-{args.index}.lock"
    lock = lock_path.open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(f"cache worker {args.index} is already active")
    layout = ROOT / f"oci-{args.index}"
    digest_dir = ROOT / "image-digests"
    local_digest_dir = ROOT / "image-local-digests"
    ready_dir = ROOT / "cache-ready"
    layout.mkdir(parents=True, exist_ok=True)
    digest_dir.mkdir(parents=True, exist_ok=True)
    local_digest_dir.mkdir(parents=True, exist_ok=True)
    ready_dir.mkdir(parents=True, exist_ok=True)
    state_path = ROOT / f"image-cache-{args.index}.json"
    failures: dict[str, int] = {}
    # A failed large layer is moved to the end of the next pass instead of
    # killing the worker and preventing unrelated images from being cached.
    for round_number in range(1, 49):
        pending = [identity for identity in assigned if not (ready_dir / identity).is_file()]
        atomic_json(state_path, {"state": "running", "worker": args.index,
                    "round": round_number, "assigned": len(assigned),
                    "ready": len(assigned) - len(pending), "pending": pending,
                    "failures": failures, "heartbeat": time.time()})
        if not pending:
            break
        for identity in pending:
            marker = ready_dir / identity
            image = f"docker://ghcr.io/scaleapi/swe-bench_pro-v2:{identity}"
            local_tag = "task-" + hashlib.sha256(identity.encode()).hexdigest()[:32]
            digest_path = digest_dir / f"{identity}.txt"
            temporary_digest = digest_dir / f"{identity}.txt.tmp"
            if not digest_path.is_file():
                print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] inspect {identity} round {round_number}", flush=True)
                result = run_capture(
                    ["skopeo", "inspect", "--retry-times", "10", "--format", "{{.Digest}}", image],
                    timeout=900,
                )
                if result.returncode != 0 or not result.stdout.startswith(b"sha256:"):
                    failures[identity] = failures.get(identity, 0) + 1
                    temporary_digest.unlink(missing_ok=True)
                    continue
                temporary_digest.write_bytes(result.stdout)
                temporary_digest.replace(digest_path)
            print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] copy {identity} round {round_number}", flush=True)
            result = run(["skopeo", "copy", "--retry-times", "10", image,
                          f"oci:{layout}:{local_tag}"], timeout=7200)
            if result.returncode != 0:
                failures[identity] = failures.get(identity, 0) + 1
                atomic_json(state_path, {"state": "retrying", "worker": args.index,
                            "round": round_number, "current": identity,
                            "assigned": len(assigned),
                            "ready": sum((ready_dir / item).is_file() for item in assigned),
                            "failures": failures, "last_exit": result.returncode,
                            "heartbeat": time.time()})
                continue
            local = run_capture(
                ["skopeo", "inspect", "--format", "{{.Digest}}", f"oci:{layout}:{local_tag}"],
                timeout=300,
            )
            # Docker-to-OCI conversion can legitimately rewrite the manifest and
            # therefore its digest.  Preserve the immutable registry digest in
            # image-digests, and separately require a parseable local OCI image.
            # Equality is not an integrity invariant unless --preserve-digests
            # is used for every historical and current copy.
            local_digest = local.stdout.decode().strip()
            if local.returncode != 0 or not local_digest.startswith("sha256:"):
                failures[identity] = failures.get(identity, 0) + 1
                print(f"local digest validation failed: {identity}", flush=True)
                continue
            (local_digest_dir / f"{identity}.txt").write_text(local_digest + "\n")
            marker.touch()
            atomic_json(state_path, {"state": "running", "worker": args.index,
                        "round": round_number, "current": identity,
                        "assigned": len(assigned),
                        "ready": sum((ready_dir / item).is_file() for item in assigned),
                        "failures": failures, "heartbeat": time.time()})
        if any(not (ready_dir / identity).is_file() for identity in assigned):
            delay = min(600, 30 * round_number)
            print(f"round {round_number} incomplete; retrying after {delay}s", flush=True)
            time.sleep(delay)
    else:
        pending = [identity for identity in assigned if not (ready_dir / identity).is_file()]
        atomic_json(state_path, {"state": "exhausted", "worker": args.index,
                    "assigned": len(assigned), "ready": len(assigned) - len(pending),
                    "pending": pending, "failures": failures, "heartbeat": time.time()})
        raise RuntimeError(f"worker {args.index} exhausted 48 rounds; pending: {pending}")
    (ROOT / f"IMAGE_CACHE_WORKER_{args.index}_READY").touch()
    if all((ROOT / f"IMAGE_CACHE_WORKER_{index}_READY").is_file() for index in (0, 1)):
        (ROOT / "IMAGE_CACHE_READY").touch()
    atomic_json(state_path, {"state": "completed", "worker": args.index,
                "assigned": len(assigned), "ready": len(assigned),
                "failures": failures, "heartbeat": time.time()})
    print(f"worker {args.index}: all {len(assigned)} images cached", flush=True)


if __name__ == "__main__":
    main()
