"""Explicit opt-in CLI; Linux disposable file-only tasks, never auto-deploy."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from .graph_runtime import GraphTaskRunner
from .graph_collaboration import CollaborativeGraphRunner
from .graph_roles import collaborator_config
from .graph_search import GraphLimits
from .lean_environment import LiveWorkspace
from .lean_protocol import LeanConfig
from .models import TaskSpec
from .retrac_adapter import RetracModelConfig, OpenAICompatibleJSONClient


def main(argv=None):
    parser = argparse.ArgumentParser(description='BestFGS collaborative-graph-v2: actor, monitor and advisor on a real search graph')
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--goal', required=True)
    parser.add_argument('--task-id', default='graph-cli-task')
    parser.add_argument('--constraint', action='append', default=[])
    parser.add_argument('--provider', choices=('openai','deepseek','dashscope'), default='deepseek')
    parser.add_argument('--model', required=True)
    parser.add_argument('--base-url')
    parser.add_argument('--api-key-env')
    parser.add_argument('--wall-seconds', type=float, default=3600)
    parser.add_argument('--max-turns', type=int, default=800)
    parser.add_argument('--max-tools', type=int, default=600)
    parser.add_argument('--advisor-calls', type=int, default=6)
    parser.add_argument('--cooperation', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--advisor-model', help='Defaults to actor model; independent role/client')
    parser.add_argument('--advisor-provider', choices=('openai','deepseek','dashscope'))
    parser.add_argument('--advisor-base-url')
    parser.add_argument('--advisor-api-key-env')
    parser.add_argument('--monitor-calls', type=int, default=12)
    parser.add_argument('--semantic-monitor', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--auto-memory', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--monitor-model', help='Defaults to actor model; independent role/client')
    parser.add_argument('--monitor-provider', choices=('openai','deepseek','dashscope'))
    parser.add_argument('--monitor-base-url')
    parser.add_argument('--monitor-api-key-env')
    parser.add_argument('--width', type=int, default=2)
    parser.add_argument('--max-nodes', type=int, default=64)
    parser.add_argument('--max-snapshots', type=int, default=64)
    args = parser.parse_args(argv)
    cfg = LeanConfig(max_turns=args.max_turns, max_tools=args.max_tools,
        wall_seconds=args.wall_seconds, max_advisor_calls=args.advisor_calls,
        max_monitor_calls=args.monitor_calls, semantic_monitor=args.semantic_monitor,
        auto_memory=args.auto_memory, memory_reliability=True, monitor_reliability=True,
        outcome_reliability=True, contrastive_mode='off', route_search=False, stagnation_control=False)
    limits = GraphLimits(width=args.width, max_nodes=args.max_nodes, max_snapshots=args.max_snapshots)
    model = RetracModelConfig.from_environment(provider=args.provider, model_name=args.model,
        base_url=args.base_url, api_key_env=args.api_key_env, temperature=0)
    model = replace(model, request_attempts=2, parse_attempts=1, timeout_seconds=60,
                    max_wall_time_seconds=120, max_tokens=4096, thinking_enabled=False)
    advisor_config=collaborator_config(model,'advisor',model_name=args.advisor_model,
        provider=args.advisor_provider,base_url=args.advisor_base_url,api_key_env=args.advisor_api_key_env)
    observer_config=(collaborator_config(model,'monitor',model_name=args.monitor_model,
        provider=args.monitor_provider,base_url=args.monitor_base_url,api_key_env=args.monitor_api_key_env)
        if cfg.semantic_monitor or cfg.auto_memory else None)
    root, seed = args.run_root.resolve(), args.workspace.resolve()
    if not seed.is_dir() or root==seed or root.is_relative_to(seed) or seed.is_relative_to(root):
        parser.error('run-root and seed workspace must be disjoint; workspace must exist')
    root.mkdir(parents=True, exist_ok=False)
    action = OpenAICompatibleJSONClient(model)
    advisor = OpenAICompatibleJSONClient(advisor_config)
    monitor = (OpenAICompatibleJSONClient(observer_config,
        diagnostics_path=root/'monitor-wire-failures.jsonl') if cfg.semantic_monitor or cfg.auto_memory else None)
    environment = LiveWorkspace(seed, root/'environment',credential_variables=tuple(filter(None,
        [args.api_key_env,args.advisor_api_key_env,args.monitor_api_key_env])))
    runner_type=CollaborativeGraphRunner if args.cooperation else GraphTaskRunner
    result = runner_type(environment,action,advisor,cfg,root/'audit',monitor_client=monitor,
        graph_limits=limits).run(TaskSpec(args.task_id,args.goal,constraints=tuple(args.constraint)))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['artifact'] and not result['error_type'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
