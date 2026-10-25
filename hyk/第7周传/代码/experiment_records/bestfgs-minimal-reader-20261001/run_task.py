"""Standalone v6.1 real-CLI entry point for an ALREADY disposable Linux sandbox.

Does not reproduce official benchmark environments or hidden grading. No auto launch.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'src'))
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
from bestfgs.monitor_config import monitor_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--goal-file', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--wall-seconds', type=int, default=7200)
    parser.add_argument('--allow-local-execution', action='store_true')
    args = parser.parse_args()
    if not args.allow_local_execution or os.name != 'posix':
        parser.error('Use a disposable Linux/WSL sandbox and explicitly pass --allow-local-execution')
    if args.out.exists(): parser.error('--out must be a new directory, outside --seed')
    # All client instances are independent; keys are only read from the environment.
    base = RetracModelConfig.from_environment(provider='deepseek', model_name=args.model,
        temperature=0, thinking_enabled=False, max_tokens=4096, timeout_seconds=90,
        max_wall_time_seconds=180, request_attempts=2, parse_attempts=1, stream_response=False)
    actor = OpenAICompatibleJSONClient(base)
    advisor = OpenAICompatibleJSONClient(replace(base, max_tokens=1536))
    monitor = OpenAICompatibleJSONClient(monitor_config(base))
    args.out.mkdir(parents=True)
    environment = LiveWorkspace(args.seed, args.out/'workspace')
    config = LeanConfig(max_turns=800, max_tools=600, wall_seconds=args.wall_seconds,
        command_seconds=300, semantic_monitor=True, auto_memory=True,
        memory_reliability=True, monitor_reliability=True, outcome_reliability=True,
        stagnation_control=True)
    result = LeanTaskRunner(environment, actor, advisor, config, args.out/'trace',
        secrets=(base.api_key,), monitor_client=monitor).run(
            TaskSpec('local-reading-task', args.goal_file.read_text(encoding='utf-8')))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
