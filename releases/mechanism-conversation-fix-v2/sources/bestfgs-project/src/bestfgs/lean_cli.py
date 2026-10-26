"""Primary v18 entry point; local execution requires a disposable Linux workspace."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
from .lean_environment import LiveWorkspace
from .lean_protocol import LeanConfig
from .lean_runtime import LeanTaskRunner
from .models import TaskSpec
from .retrac_adapter import RetracModelConfig, OpenAICompatibleJSONClient


def main(argv=None):
    parser = argparse.ArgumentParser(description='BestFGS v18: continuous CLI execution with on-demand exploration advice')
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--run-root', required=True, type=Path)
    parser.add_argument('--goal', required=True)
    parser.add_argument('--task-id', default='cli-task')
    parser.add_argument('--constraint', action='append', default=[])
    parser.add_argument('--provider', choices=('openai','deepseek','dashscope'), default='deepseek')
    parser.add_argument('--model', required=True, help='Explicit model ID; no silent model upgrade')
    parser.add_argument('--base-url')
    parser.add_argument('--api-key-env')
    parser.add_argument('--wall-seconds', type=float, default=3600)
    parser.add_argument('--max-turns', type=int, default=800, help='All model requests, including adviser requests')
    parser.add_argument('--max-tools', type=int, default=600)
    parser.add_argument('--advisor-calls', type=int, default=6)
    args = parser.parse_args(argv)
    config = LeanConfig(wall_seconds=args.wall_seconds, max_turns=args.max_turns,
                        max_tools=args.max_tools, max_advisor_calls=args.advisor_calls)
    model = RetracModelConfig.from_environment(provider=args.provider, model_name=args.model,
        base_url=args.base_url, api_key_env=args.api_key_env, temperature=0)
    model = replace(model, request_attempts=2, parse_attempts=1,
                    timeout_seconds=60, max_wall_time_seconds=120, max_tokens=4096,
                    thinking_enabled=False)
    action = OpenAICompatibleJSONClient(model)
    advisor = OpenAICompatibleJSONClient(replace(model, max_tokens=1536))
    root = args.run_root.resolve()
    if root == args.workspace.resolve() or root.is_relative_to(args.workspace.resolve()):
        parser.error('run-root must be outside the task workspace')
    root.mkdir(parents=True, exist_ok=False)
    environment = LiveWorkspace(args.workspace, root/'environment',
                                credential_variables=tuple(filter(None, [args.api_key_env])))
    result = LeanTaskRunner(environment, action, advisor, config, output=root/'audit').run(
        TaskSpec(args.task_id, args.goal, constraints=tuple(args.constraint)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['artifact'] and not result['error_type'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
