"""Build and verify an offline handoff ZIP using only the Python standard library."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = ("README.md", "pyproject.toml", ".gitignore")
DIRECTORIES = ("src", "tests", "scripts", "docs", "vendor-contracts")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "dist", "build"}


def payloads() -> dict[str, bytes]:
    selected = [ROOT / name for name in TOP_FILES]
    for name in DIRECTORIES:
        selected.extend(path for path in (ROOT / name).rglob("*") if path.is_file())
    result = {}
    for path in sorted(selected):
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS or part.startswith(".test-tmp") or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo", ".tmp"}:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Handoff source must stay inside the project: " + str(relative))
        result["recuris/" + relative.as_posix()] = path.read_bytes()
    return result


def main() -> None:
    files = payloads()
    manifest = {
        "schema_version": 1,
        "package": "recuris-longcli",
        "contains_benchmark_results": False,
        "files": [{"path": name, "sha256": sha256(data).hexdigest(), "bytes": len(data)}
                  for name, data in sorted(files.items())],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    files["recuris/HANDOFF_MANIFEST.json"] = manifest_bytes
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    archive = destination / "recuris-handoff.zip"
    temporary = archive.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
            for name, data in sorted(files.items()):
                item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                item.create_system = 3
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
                output.writestr(item, data, compresslevel=9)
        with zipfile.ZipFile(temporary) as check:
            if check.testzip() is not None or set(check.namelist()) != set(files):
                raise ValueError("Archive integrity or file-list verification failed")
            for name, data in files.items():
                if check.read(name) != data:
                    raise ValueError("Archive payload changed: " + name)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    (destination / "HANDOFF_MANIFEST.json").write_bytes(manifest_bytes)
    digest = sha256(archive.read_bytes()).hexdigest()
    (destination / "SHA256SUMS").write_text(digest + "  " + archive.name + "\n", encoding="ascii")
    print(json.dumps({"archive": str(archive), "sha256": digest,
                      "source_files": len(manifest["files"]), "zip_entries": len(files)}, indent=2))


if __name__ == "__main__":
    main()
