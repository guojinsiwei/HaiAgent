"""Run local offline checks; no Docker, API key or cloud access."""
import importlib
import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    for module in ('bestfgs.lean_runtime', 'bestfgs.retrac_adapter', 'haiagent.runtime',
                   'haiagent.model', 'terminal_context'):
        loaded = importlib.import_module(module)
        if not Path(loaded.__file__).resolve().is_relative_to(ROOT):
            raise RuntimeError('Dependency escaped extracted unit: '+module)
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
