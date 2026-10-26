"""Provider adapter for the frozen BestFGS v12 paired SWE runner.

The algorithm implementation remains in /mnt/lizh639/BestFGS-blocking-memory-v12.
This file changes only the model service configuration from the official
DeepSeek endpoint to Alibaba Model Studio's OpenAI-compatible endpoint.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys

CODE = Path("/mnt/lizh639/BestFGS-blocking-memory-v12")
sys.path[:0] = [str(CODE), str(CODE / "src")]

import run_comparison as frozen


def adapter_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def common_args(args):
    result = [
        "--engine", "evidence",
        "--provider", "dashscope",
        "--model", args.model,
        "--base-url", args.base_url,
        "--api-key-env", "DASHSCOPE_API_KEY",
        "--temperature", str(args.temperature),
        "--reasoning-effort", args.reasoning_effort,
        "--solve-reasoning-effort", args.reasoning_effort,
        "--max-iterations", str(args.max_iterations),
        "--max-tool-calls", str(args.max_tool_calls),
        "--max-commands-per-action", str(args.max_commands),
        "--budget-multiplier", "1",
        "--no-adaptive-budget",
        "--success-judge-mode", "off",
        "--comparison-metrics",
        "--model-timeout", "90",
        "--model-max-wall-time", "600",
        "--model-request-attempts", "5",
        "--model-parse-attempts", "3",
        "--model-retry-interval", "2",
        "--model-max-retry-interval", "30",
    ]
    if args.top_p is not None:
        result += ["--top-p", str(args.top_p)]
    return result


_protocol_for = frozen.protocol_for


def protocol_for(args, plan):
    protocol, prepared, missing = _protocol_for(args, plan)
    protocol["provider_adapter_sha256"] = adapter_sha256()
    protocol["model_service"] = {
        "provider": "alibaba_model_studio",
        "api_protocol": "openai_compatible_chat_completions",
        "model": "deepseek-v3.1",
        "thinking": "enabled",
        "reasoning_effort_mapping": "BestFGS high -> enable_thinking=true",
        "credential_env": "DASHSCOPE_API_KEY",
        "endpoint_frozen_in_protocol": True,
    }
    protocol["study_scope"] = (
        "Exploratory same-model paired test of harness benefit at a lower model tier; "
        "not a direct estimate of model-capability causality."
    )
    return protocol, prepared, missing


frozen.common_args = common_args
frozen.protocol_for = protocol_for

# The frozen runner checks this legacy variable before entering its paid run.
# It is a non-secret sentinel; the actual provider reads DASHSCOPE_API_KEY.
os.environ.setdefault("DEEPSEEK_API_KEY", "unused-provider-sentinel")

if __name__ == "__main__":
    raise SystemExit(frozen.main())
