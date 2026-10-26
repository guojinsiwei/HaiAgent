"""Small reliability helpers shared by the benchmark launchers."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Replace one artifact atomically so interruption cannot leave half JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def implementation_sha256(project_root: Path) -> str:
    """Fingerprint the runner and algorithm implementation, excluding results/tests."""

    project_root = project_root.resolve()
    candidates = list((project_root / "src").rglob("*.py"))
    candidates.extend(project_root.glob("benchmark_*.py"))
    candidates.extend(project_root.glob("run_swebench*.py"))
    candidates.extend(project_root.glob("run_terminal_bench*.py"))
    candidates.extend(project_root.glob("run_notebook*.py"))
    candidates.extend(project_root.glob("prepare_swe_*.py"))
    candidates.extend(project_root.glob("swe_batch*.py"))
    candidates.extend(project_root.glob("build_swe_batch.py"))
    candidates.extend(project_root.glob("evaluate_swe_batch.py"))
    candidates.append(project_root / "pyproject.toml")
    digest = hashlib.sha256()
    for path in sorted(
        {item.resolve() for item in candidates if item.is_file()},
        key=lambda item: item.relative_to(project_root).as_posix(),
    ):
        relative = path.relative_to(project_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def public_endpoint(url: str) -> str:
    """Record endpoint provenance without query strings or user information."""

    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.hostname:
        return url.split("?", 1)[0]
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.hostname}{port}{path}"


def base_manifest(*, benchmark: str, run_id: str, project_root: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "benchmark": benchmark,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "implementation_sha256": implementation_sha256(project_root),
        "launcher_runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }
