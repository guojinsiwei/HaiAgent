#!/usr/bin/env python3
"""Copy the task directories named in an id list into a new dataset directory.

    python3 v2/tooling/make_subset.py v2/tasks v2/hard51_ids.txt datasets/hard51
"""
import shutil, sys
from pathlib import Path

src, ids_file, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
ids = [l.strip() for l in ids_file.read_text().splitlines() if l.strip()]
out.mkdir(parents=True, exist_ok=True)
for i in ids:
    if not (src / i).is_dir():
        sys.exit(f"missing task dir: {src / i}")
    shutil.copytree(src / i, out / i, dirs_exist_ok=True)
print(f"copied {len(ids)} tasks to {out}")
