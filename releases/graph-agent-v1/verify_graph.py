"""Run offline acceptance and preserve the actual unittest result."""
import json
from pathlib import Path
import platform
import time
import unittest

ROOT=Path(__file__).resolve().parent


def main():
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    report=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        python=platform.python_version(),platform=platform.system(),updated=time.time(),
        model_api_calls=0,cloud_deployed=False,
        actual_file_snapshot_fixture=True,
        linux_production_executor_verified=False,
        benchmark_performance_verified=False)
    (ROOT/'offline-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
