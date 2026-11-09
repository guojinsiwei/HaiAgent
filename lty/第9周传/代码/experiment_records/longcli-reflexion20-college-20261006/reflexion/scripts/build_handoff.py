"""Create a source-only handoff archive; no installation, network or experiments."""

from hashlib import sha256
from pathlib import Path
import zipfile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    files = [root / name for name in ("README.md", "pyproject.toml", ".gitignore")]
    for folder, extensions in (
        ("src", {".py"}), ("tests", {".py"}), ("docs", {".md", ".json"}),
        ("scripts", {".py", ".sh"}),
    ):
        files.extend(path for path in (root / folder).rglob("*")
                     if path.is_file() and path.suffix in extensions and "__pycache__" not in path.parts)
    files.extend(path for path in (root / "vendor-contracts").iterdir() if path.is_file())
    files = sorted(set(files), key=lambda p: p.relative_to(root).as_posix())
    manifest = "".join(f"{sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n"
                       for path in files)
    (root / "MANIFEST.sha256").write_text(manifest, encoding="utf-8", newline="\n")
    output = root / "dist" / "reflexion-handoff.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [*files, root / "MANIFEST.sha256"]:
            archive.write(path, "reflexion/" + path.relative_to(root).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive CRC verification failed")
        for path in files:
            data = archive.read("reflexion/" + path.relative_to(root).as_posix())
            if sha256(data).digest() != sha256(path.read_bytes()).digest():
                raise RuntimeError(f"Archive content mismatch: {path.name}")
    digest = sha256(output.read_bytes()).hexdigest()
    (root / "dist" / "reflexion-handoff.zip.sha256").write_text(
        f"{digest}  {output.name}\n", encoding="utf-8", newline="\n")
    print(f"Archive: {output}\nSource files: {len(files)}\nSHA256: {digest}")


if __name__ == "__main__":
    main()
