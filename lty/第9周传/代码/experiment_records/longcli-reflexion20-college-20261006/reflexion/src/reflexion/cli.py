"""Offline configuration and installation checks. This CLI never runs a task."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib
import json
import os
import sys

from . import __version__
from .engine import ReflexionConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reflexion LongCLI adapter: offline checks (no model/API/experiment calls)")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config", help="Print the default algorithm configuration as JSON")
    doctor = sub.add_parser("doctor", help="Check model configuration and native adapter import without network access")
    doctor.add_argument("--model", default=None)
    doctor.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    args = parser.parse_args(argv)
    if args.command == "config":
        print(json.dumps(asdict(ReflexionConfig()), indent=2))
        return 0
    model = args.model or os.environ.get("DEEPSEEK_MODEL") or os.environ.get("OPENAI_MODEL")
    checks = {
        "python_version": sys.version.split()[0],
        "python_meets_longcli_3_12": sys.version_info >= (3, 12),
        "model_configured": bool(model and model.strip()),
        "api_key_variable": args.api_key_env,
        "api_key_present": bool(os.environ.get(args.api_key_env, "").strip()),
        "native_adapter_importable": False,
        "network_contacted": False,
        "note": "Importability does not verify the LongCLI fork/commit, Docker, datasets, or endpoint compatibility.",
    }
    try:
        module = importlib.import_module("reflexion.longcli")
        checks["native_adapter_importable"] = issubclass(module.ReflexionAgent, module.BaseAgent)
    except ImportError:
        checks["adapter_error"] = "Install the pinned official LongCLI-Bench checkout in this Python environment."
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if all(checks[key] for key in (
        "python_meets_longcli_3_12", "model_configured", "api_key_present", "native_adapter_importable"
    )) else 1

