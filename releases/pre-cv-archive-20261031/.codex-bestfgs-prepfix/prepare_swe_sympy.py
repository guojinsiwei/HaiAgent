"""Prepare one existing development issue using public metadata only.

No HF cache, gold patch, hidden tests, or model API requests are needed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from benchmark_runtime import atomic_write_json, atomic_write_text
from benchmark_splits import reject_frozen_overlap

INSTANCE = "sympy__sympy-16450"
BASE_COMMIT = "aefdd023dc4f73c441953ed51f5f05a076f0862f"
REPOSITORY = "https://github.com/sympy/sympy.git"
PUBLIC_GOAL = """Posify ignores is_finite assmptions
Posify removes a finite assumption from a symbol:
```python
x = Symbol('x', finite=True)
x._assumptions
# {'finite': True, 'infinite': False, 'commutative': True}
x.is_finite
# True
xp, _ = posify(x)
xp._assumptions
# {'positive': True, 'real': True, 'hermitian': True,
#  'imaginary': False, 'negative': False, 'nonnegative': True,
#  'nonzero': True, 'zero': False, 'complex': True,
#  'nonpositive': False, 'commutative': True}
print(xp.is_finite)
# None
```
I think that posify should preserve the finiteness assumption. Possibly other assumptions should be preserved as well (integer, rational, prime, even, odd...).
"""


def git(seed: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=seed, check=True, stdout=subprocess.PIPE, text=True, timeout=300)
    return result.stdout.strip()


def prepare(tasks_root: Path, task_python: Path) -> Path:
    reject_frozen_overlap([INSTANCE], benchmark="swebench", allow_frozen_test_set=False)
    tasks_root = tasks_root.resolve()
    task_python = task_python.resolve()
    if not task_python.is_file():
        raise ValueError(f"Create the task Python environment first: {task_python}")
    seed = tasks_root / INSTANCE
    if seed.exists():
        if not (seed / ".git").is_dir() or git(seed, "rev-parse", "HEAD") != BASE_COMMIT or git(seed, "status", "--porcelain"):
            raise ValueError(f"Existing seed is not a clean checkout at the required commit; refusing to overwrite: {seed}")
    else:
        seed.mkdir(parents=True)
        print("[prepare] Downloading only the base commit; no later solution history", flush=True)
        git(seed, "init")
        git(seed, "remote", "add", "origin", REPOSITORY)
        git(seed, "fetch", "--depth", "1", "--no-tags", "origin", BASE_COMMIT)
        git(seed, "checkout", "--detach", "FETCH_HEAD")
        if git(seed, "rev-parse", "HEAD") != BASE_COMMIT:
            raise ValueError("Downloaded commit mismatch")
    # Import from this checkout, not a global editable install pointing at the seed.
    probe = subprocess.run([str(task_python), "-c", "import sys, pathlib, sympy, mpmath; assert sys.version_info[:2] == (3,9); assert pathlib.Path(sympy.__file__).resolve().is_relative_to(pathlib.Path.cwd()); print('Python:',sys.version.split()[0]); print('SymPy:',sympy.__version__); print('Source:',sympy.__file__); print('mpmath:',mpmath.__version__)"], cwd=seed, check=True, capture_output=True, text=True, timeout=30)
    print(probe.stdout, flush=True)
    # Public existing smoke tests, not issue-specific hidden verifier tests.
    print("[prepare] Running public existing symbol tests; this is not official grading", flush=True)
    subprocess.run([str(task_python), "bin/test", "-C", "sympy/core/tests/test_symbol.py"], cwd=seed, check=True, timeout=300)
    if git(seed, "status", "--porcelain"):
        raise ValueError("Preparation left an unclean seed; refusing to write a task manifest")
    manifest = tasks_root / "sympy-dev-task.json"
    payload = {
        "schema_version": 1, "benchmark": "swebench",
        "tasks": [{"id": INSTANCE, "workspace": str(seed), "base_commit": BASE_COMMIT,
                   "goal": PUBLIC_GOAL,
                   "success_criteria": ["Fix the publicly reported posify assumption-preservation behavior and verify it without introducing regressions."],
                   "constraints": ["Use python from PATH for task commands; this is the prepared Python 3.9 runtime. Do not use the BestFGS agent's Python 3.11 for SymPy.",
                                   "Only modify task source code. Do not modify existing tests; temporary reproduction scripts may be used for public functional verification.",
                                   "Do not read reference patches, hidden evaluation tests, later repository history, or online solutions.",
                                   "Do not install packages or alter system services during search; task dependencies are already prepared."]}]
    }
    if manifest.exists():
        import json
        if json.loads(manifest.read_text(encoding="utf-8")) != payload:
            raise ValueError(f"Existing manifest differs; refusing to overwrite: {manifest}")
    atomic_write_json(manifest, payload)
    freeze = subprocess.run([str(task_python), "-m", "pip", "freeze"], check=True, capture_output=True, text=True, timeout=30)
    atomic_write_text(tasks_root / "sympy-task-pip-freeze.txt", freeze.stdout)
    atomic_write_json(tasks_root / "sympy-preparation.json", {"instance_id": INSTANCE, "base_commit": BASE_COMMIT,
        "repository": REPOSITORY, "task_python": str(task_python),
        "official_evaluation": False, "public_existing_symbol_tests_passed": True,
        "dataset": "SWE-bench/SWE-bench_Verified", "public_metadata_cache_id": "78f471bf655a3137b2e8a75af1501690ec009ec3"})
    print(f"[ready] Task manifest: {manifest}", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-root", type=Path, required=True)
    parser.add_argument("--task-python", type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.tasks_root, args.task_python)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"Preparation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
