"""Use the bundled DHv1, never an unrelated globally installed bestfgs package."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_cli import main

if __name__ == '__main__':
    raise SystemExit(main())
