"""Offline demonstration and installation checks; actual tasks use the benchmark."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib
import json
import os
from pathlib import Path

from .audit import JsonlLogger
from .client import ModelReply
from .engine import RetracConfig, RetracRunner, STATE_HEADINGS


class DemoClient:
    def __init__(self):
        self.round = 0

    def complete(self, messages, *, purpose, deadline_monotonic=None):
        if purpose == "compress":
            content = "\n".join(f"{i}) {name}\n" + (
                "Observed: target.txt still says broken. The first proposed repair was not applied."
                if i in (0, 1, 4, 5) else "Next rollout should write fixed and read it back; no official verifier was called."
            ) for i, name in enumerate(STATE_HEADINGS))
        else:
            self.round += 1
            if self.round == 1:
                commands = [{"keystrokes": "cat target.txt\n", "duration": 0}]
                answer = ""
            elif self.round == 2:
                commands = []
                answer = "Not yet repaired"
            elif self.round == 3:
                commands = [{"keystrokes": "printf fixed > target.txt\n", "duration": 0},
                            {"keystrokes": "cat target.txt\n", "duration": 0}]
                answer = ""
            else:
                commands = []
                answer = "Observed target.txt contains fixed"
            content = json.dumps({"analysis": "Scripted fixture", "commands": commands,
                                  "task_complete": not commands, "final_answer": answer})
        return ModelReply(content, 0, 0, "stop")


class DemoTerminal:
    """In-memory fixture: command strings never reach a host shell."""
    def __init__(self):
        self.value = "broken"

    def observe(self):
        return f"Simulated terminal; target.txt={self.value}"

    def execute(self, keystrokes, duration):
        if keystrokes == "cat target.txt\n":
            return self.value
        if keystrokes == "printf fixed > target.txt\n":
            self.value = "fixed"
            return ""
        raise ValueError("Unsupported demo fixture command")


def main(argv=None):
    parser = argparse.ArgumentParser(description="RE-TRAC / LongCLI-Bench adapter (DeepSeek compatible)")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run a deterministic offline two-rollout fixture; no API or shell calls")
    demo.add_argument("--output", type=Path, default=Path("runs/demo"))
    commands.add_parser("doctor", help="Check installed benchmark adapter and environment variable presence")
    args = parser.parse_args(argv)
    if args.command == "demo":
        if args.output.exists() and any(args.output.iterdir()):
            parser.error("Demo output must be a new or empty directory")
        terminal = DemoTerminal()
        result = RetracRunner(DemoClient(), RetracConfig(rounds=2), JsonlLogger(args.output)).run(
            "Change target.txt from broken to fixed and inspect its contents.", terminal)
        payload = asdict(result)
        payload["fixture_passed"] = terminal.value == "fixed" and result.stop_reason == "rounds_completed"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["fixture_passed"] else 1
    checks = {name: bool(os.environ.get(name)) for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL")}
    try:
        module = importlib.import_module("retrac.longcli")
        checks["longcli_adapter_import"] = bool(module.RetracAgent)
    except ImportError as exc:
        checks["longcli_adapter_import"] = False
        checks["import_error"] = str(exc)
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if all(checks.get(name) for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "longcli_adapter_import")) else 1
