"""Run offline regressions and write an auditable receipt; never a benchmark score.

Only loopback sockets are allowed, for the existing fake API transport tests.
Real controller credentials are removed before importing the test suite.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import platform
import socket
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default="test*.py")
    parser.add_argument("--output", type=Path, default=ROOT / "VALIDATION_V12.json")
    args = parser.parse_args(argv)
    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        os.environ.pop(key, None)
    original_connect = socket.socket.connect
    original_getaddrinfo = socket.getaddrinfo

    def assert_local(host):
        if host == "localhost":
            return
        try:
            allowed = ipaddress.ip_address(host).is_loopback
        except (ValueError, TypeError):
            allowed = False
        if not allowed:
            raise AssertionError("Offline regression attempted non-loopback network access")

    def local_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            assert_local(address[0])
        return original_connect(sock, address)

    def local_resolution(host, *positional, **kwargs):
        assert_local(host)
        return original_getaddrinfo(host, *positional, **kwargs)

    from benchmark_runtime import implementation_sha256, atomic_write_json
    started = time.monotonic()
    with patch.object(socket.socket, "connect", local_connect), patch.object(socket, "getaddrinfo", local_resolution):
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=args.pattern)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    report = {
        "version": "blocking-cli-v12", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Offline regression and synthetic integration; NOT SWE/Terminal benchmark performance",
        "pattern": args.pattern, "implementation_sha256": implementation_sha256(ROOT),
        "python": sys.version, "platform": platform.platform(),
        "tests_run": result.testsRun,
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "successful": result.wasSuccessful(), "duration_seconds": round(time.monotonic() - started, 3),
        "network_policy": "in-process sockets limited to loopback fake API fixtures",
        "paid_benchmark_started": False, "cloud_modified": False,
    }
    atomic_write_json(args.output, report)
    print(json.dumps({"receipt": str(args.output.resolve()), "tests_run": report["tests_run"],
                      "successful": report["successful"]}, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
