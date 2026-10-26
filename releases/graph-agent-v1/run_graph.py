"""Explicit graph-only entry point, independent of historical default CLIs."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/'sources/bestfgs-project/src'))
from bestfgs.graph_cli import main

if __name__ == '__main__':
    raise SystemExit(main())
