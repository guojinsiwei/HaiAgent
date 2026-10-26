"""Keep core runtime fixtures in the release acceptance suite (no live API)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from test_lean import LeanTests, LocalEnvironmentTests
