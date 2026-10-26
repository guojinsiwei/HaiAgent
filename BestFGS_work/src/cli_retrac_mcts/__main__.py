from __future__ import annotations

import argparse
import json
import logging
import math
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .agent import TaskRunner
from .environment import EnvironmentConfig, ForkedWorkspaceEnvironment
from .mcts import MCTSConfig, adapt_search_budget
from .models import TaskSpec
from .retrac_adapter import (
    PROVIDER_DEFAULTS,
    OpenAICompatibleJSONClient,
    RetracModelConfig,
    RetracPolicyAdapter,
)
from .semantic import semantic_coverage_rate
from .success_judge import IndependentSuccessJudge


#真实模型的最小启动入口，不包含实验编排、批量评测和跨任务记忆
def build_parser() -> argparse.ArgumentParser:
    defaults = MCTSConfig()
    parser = argparse.ArgumentParser(
        description="运行RE-TRAC结构化压缩与阶段自适应语义Best-First图搜索智能体"
    )
    parser.add_argument("--goal", required=True, help="需要智能体完成的任务")
    parser.add_argument(
        "--success-criterion",
        action="append",
        default=[],
        help="成功标准，可重复提供；未提供时使用goal本身",
    )
    parser.add_argument("--constraint", action="append", default=[], help="任务约束，可重复提供")
    parser.add_argument("--workspace", type=Path, required=True, help="只作为种子的任务工作区")
    parser.add_argument("--run-root", type=Path, help="图搜索隔离快照目录，默认使用系统临时目录")

    parser.add_argument(
        "--provider",
        choices=("openai", "deepseek", "dashscope"),
        default="openai",
        help="模型服务商；支持openai、deepseek与阿里云百炼dashscope",
    )
    parser.add_argument("--model", help="模型名；默认读取所选provider对应的环境变量")
    parser.add_argument("--base-url", help="兼容API地址；DeepSeek已有官方默认地址")
    parser.add_argument("--api-key-env", help="覆盖所选provider默认的API Key环境变量名")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "high", "max"),
        default="high",
        help="探索、转移评估和上下文压缩使用的思考强度",
    )
    parser.add_argument(
        "--solve-reasoning-effort",
        choices=("low", "high", "max"),
        default="max",
        help="求解阶段生成候选动作使用的思考强度",
    )
    parser.add_argument(
        "--model-timeout",
        type=int,
        default=90,
        help="模型连续无任何SSE数据或保活消息时的空闲超时秒数",
    )
    parser.add_argument(
        "--model-max-wall-time",
        type=int,
        default=600,
        help="单次模型请求允许的绝对总时长秒数",
    )
    parser.add_argument("--model-request-attempts", type=int, default=5)
    parser.add_argument("--model-parse-attempts", type=int, default=3)
    parser.add_argument("--model-retry-interval", type=float, default=2.0)
    parser.add_argument("--model-max-retry-interval", type=float, default=30.0)
    parser.add_argument(
        "--no-json-response-format",
        action="store_true",
        help="模型服务不支持response_format时使用",
    )

    parser.add_argument("--max-iterations", type=int, default=defaults.max_iterations)
    parser.add_argument("--max-tool-calls", type=int, default=defaults.max_total_tool_calls)
    parser.add_argument(
        "--budget-multiplier",
        type=float,
        default=1.0,
        help="未验证成功时分段续算的硬上限倍数（默认1，不续算；大于1增加API消耗）",
    )
    parser.add_argument("--initial-branches", type=int, default=defaults.initial_branching_factor)
    parser.add_argument("--expansion-width", type=int, default=defaults.expansion_width)
    parser.add_argument(
        "--max-expansion-batches",
        type=int,
        default=defaults.max_expansion_batches_per_node,
    )
    parser.add_argument("--max-commands-per-action", type=int, default=defaults.max_commands_per_macro_action)
    parser.add_argument(
        "--semantic-coverage-switch-threshold",
        type=float,
        default=defaults.semantic_coverage_switch_threshold,
        help="语义覆盖率引导平滑衰减至0的阈值",
    )
    parser.add_argument(
        "--recommend-rule-weight",
        type=float,
        default=defaults.recommend_rule_weight,
        help="recommend任务规则二值衰减项的权重",
    )
    parser.add_argument(
        "--rule-candidate-limit",
        type=int,
        default=defaults.rule_candidate_limit,
        help="每个节点最多交给模型判断的Top-k任务规则数",
    )
    parser.add_argument(
        "--post-success-iterations",
        type=int,
        default=defaults.post_success_iterations,
        help="首个经独立验证的成功节点保存后继续探索的轮数（默认0，即立即结束）",
    )
    parser.add_argument(
        "--selection-mode",
        choices=("root", "working", "hybrid", "exploit", "plore_ploit"),
        default=defaults.selection_mode,
        help=(
            "兼容动作生成策略；BestFGS的实际选择始终由全局阶段自适应优先队列完成"
        ),
    )
    parser.add_argument(
        "--hybrid-root-interval",
        type=int,
        default=defaults.hybrid_root_interval,
        help="hybrid模式每隔多少轮从根节点做一次全局探索",
    )
    parser.add_argument(
        "--base-children-per-node",
        type=int,
        default=defaults.base_children_per_node,
        help="没有额外语义压力时的基础树宽（默认3）",
    )
    parser.add_argument(
        "--max-children-per-node",
        type=int,
        default=defaults.max_children_per_node,
        help="语义需求驱动树宽的硬上限（默认6），不随访问次数增长",
    )
    parser.add_argument(
        "--frontier-max-per-direction",
        type=int,
        default=defaults.frontier_max_entries_per_direction,
        help="全局活跃前沿中每个语义方向最多保留的候选数（默认2）",
    )
    parser.add_argument(
        "--frontier-stale-after-iterations",
        type=int,
        default=defaults.frontier_stale_after_iterations,
        help="语义方向连续多少轮没有新证据后暂停（默认4）",
    )
    parser.add_argument(
        "--frontier-stale-min-attempts",
        type=int,
        default=defaults.frontier_stale_min_attempts,
        help="启用停滞判断前至少执行该方向多少次（默认2）",
    )
    parser.add_argument(
        "--disable-semantic-node-merge",
        action="store_true",
        help="关闭同环境指纹内的保守语义等价节点合并，供消融实验使用",
    )
    parser.add_argument(
        "--semantic-merge-fact-threshold",
        type=float,
        default=defaults.semantic_merge_fact_threshold,
    )
    parser.add_argument(
        "--semantic-merge-issue-threshold",
        type=float,
        default=defaults.semantic_merge_issue_threshold,
    )
    parser.add_argument(
        "--no-adaptive-budget",
        action="store_true",
        help="关闭题面复杂度三级预算调度，严格使用传入的基础预算",
    )
    parser.add_argument(
        "--allow-unverified-success",
        action="store_true",
        help="允许模型在没有成功测试/构建命令时声明成功（benchmark不建议）",
    )
    parser.add_argument(
        "--success-judge-mode",
        choices=("off", "audit", "required"),
        default="required",
        help=(
            "独立成功审计：required会控制停止，audit只记录，off保留旧逻辑；"
            "真实评测默认required"
        ),
    )
    parser.add_argument(
        "--success-judge-provider",
        choices=("openai", "deepseek", "dashscope"),
        help="独立审计模型服务商；默认沿用求解模型服务商",
    )
    parser.add_argument(
        "--success-judge-model",
        help="独立审计模型名；默认读取SUCCESS_JUDGE_MODEL或沿用求解模型",
    )
    parser.add_argument(
        "--success-judge-base-url",
        help="独立审计兼容API地址；默认读取SUCCESS_JUDGE_API_BASE或沿用求解地址",
    )
    parser.add_argument(
        "--success-judge-api-key-env",
        help="独立审计API Key环境变量名；默认优先SUCCESS_JUDGE_API_KEY",
    )
    parser.add_argument(
        "--success-judge-max-calls",
        type=int,
        default=2,
        help="每题独立成功审计的实际模型调用上限（默认2）",
    )
    parser.add_argument(
        "--allow-executable",
        action="append",
        default=[],
        help="可选的可执行程序白名单，可重复提供",
    )
    parser.add_argument("--quiet", action="store_true", help="只显示警告、错误和最终JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s | %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        parser.error(f"workspace不是目录: {workspace}")

    budget_text = "\n".join(
        (args.goal, *args.success_criterion, *args.constraint)
    )
    if args.no_adaptive_budget:
        adjusted_iterations = args.max_iterations
        adjusted_tool_calls = args.max_tool_calls
        budget_level = "disabled"
        budget_reasons = ("adaptive scheduling disabled",)
    else:
        budget = adapt_search_budget(
            budget_text,
            base_iterations=args.max_iterations,
            base_tool_calls=args.max_tool_calls,
        )
        adjusted_iterations = budget.max_iterations
        adjusted_tool_calls = budget.max_total_tool_calls
        budget_level = budget.complexity
        budget_reasons = budget.reasons

    try:
        model_config = RetracModelConfig.from_environment(
            provider=args.provider,
            model_name=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
            temperature=args.temperature,
            top_p=args.top_p,
            reasoning_effort=args.reasoning_effort,
            solve_reasoning_effort=args.solve_reasoning_effort,
            timeout_seconds=args.model_timeout,
            max_wall_time_seconds=args.model_max_wall_time,
            request_attempts=args.model_request_attempts,
            parse_attempts=args.model_parse_attempts,
            retry_interval_seconds=args.model_retry_interval,
            max_retry_interval_seconds=args.model_max_retry_interval,
            use_json_response_format=not args.no_json_response_format,
            max_commands_per_action=args.max_commands_per_action,
        )
        mcts_config = MCTSConfig(
            max_iterations=adjusted_iterations,
            initial_branching_factor=args.initial_branches,
            expansion_width=args.expansion_width,
            max_expansion_batches_per_node=args.max_expansion_batches,
            max_commands_per_macro_action=args.max_commands_per_action,
            max_total_tool_calls=adjusted_tool_calls,
            budget_multiplier=args.budget_multiplier,
            semantic_coverage_switch_threshold=(
                args.semantic_coverage_switch_threshold
            ),
            recommend_rule_weight=args.recommend_rule_weight,
            rule_candidate_limit=args.rule_candidate_limit,
            post_success_iterations=args.post_success_iterations,
            require_successful_verification=(
                not args.allow_unverified_success
            ),
            success_judge_mode=args.success_judge_mode,
            selection_mode=args.selection_mode,
            hybrid_root_interval=args.hybrid_root_interval,
            base_children_per_node=args.base_children_per_node,
            max_children_per_node=args.max_children_per_node,
            frontier_max_entries_per_direction=args.frontier_max_per_direction,
            frontier_stale_after_iterations=args.frontier_stale_after_iterations,
            frontier_stale_min_attempts=args.frontier_stale_min_attempts,
            semantic_node_merge=not args.disable_semantic_node_merge,
            semantic_merge_fact_threshold=args.semantic_merge_fact_threshold,
            semantic_merge_issue_threshold=args.semantic_merge_issue_threshold,
        )
        mcts_config.validate()
        if args.success_judge_max_calls <= 0:
            raise ValueError("success_judge_max_calls must be positive")
    except ValueError as error:
        parser.error(str(error))

    task = TaskSpec.create(
        args.goal,
        success_criteria=tuple(args.success_criterion) or (args.goal,),
        constraints=tuple(args.constraint),
    )
    run_root = (args.run_root or Path(tempfile.gettempdir()) / "cli_retrac_mcts" / task.task_id)
    checkpoint_path = run_root / "search_checkpoint.json"
    environment = ForkedWorkspaceEnvironment(
        seed_workspace=workspace,
        run_root=run_root,
        config=EnvironmentConfig(),
        allowed_executables=set(args.allow_executable) if args.allow_executable else None,
    )
    policy = RetracPolicyAdapter(model_config)
    success_judge = None
    judge_config = None
    if args.success_judge_mode != "off":
        judge_provider = (
            args.success_judge_provider
            or os.getenv("SUCCESS_JUDGE_PROVIDER")
            or model_config.provider
        )
        if judge_provider not in PROVIDER_DEFAULTS:
            parser.error(f"unsupported success judge provider: {judge_provider}")
        specific_key_env = args.success_judge_api_key_env or "SUCCESS_JUDGE_API_KEY"
        if not os.getenv(specific_key_env):
            specific_key_env = (
                args.api_key_env
                or PROVIDER_DEFAULTS[judge_provider].api_key_env
            )
        try:
            judge_config = RetracModelConfig.from_environment(
                provider=judge_provider,
                model_name=(
                    args.success_judge_model
                    or os.getenv("SUCCESS_JUDGE_MODEL")
                    or (
                        model_config.model_name
                        if judge_provider == model_config.provider
                        else None
                    )
                ),
                base_url=(
                    args.success_judge_base_url
                    or os.getenv("SUCCESS_JUDGE_API_BASE")
                    or (
                        model_config.base_url
                        if judge_provider == model_config.provider
                        else None
                    )
                ),
                api_key_env=specific_key_env,
                temperature=0.0,
                top_p=None,
                reasoning_effort="high",
                solve_reasoning_effort="high",
                timeout_seconds=args.model_timeout,
                max_wall_time_seconds=args.model_max_wall_time,
                request_attempts=args.model_request_attempts,
                parse_attempts=1,
                retry_interval_seconds=args.model_retry_interval,
                max_retry_interval_seconds=args.model_max_retry_interval,
                use_json_response_format=not args.no_json_response_format,
                max_commands_per_action=args.max_commands_per_action,
            )
        except ValueError as error:
            parser.error(f"success judge配置错误: {error}")
        success_judge = IndependentSuccessJudge(
            OpenAICompatibleJSONClient(judge_config),
            max_calls=args.success_judge_max_calls,
        )
    logging.getLogger(__name__).info(
        "[任务] 已加载配置：provider=%s，model=%s，workspace=%s",
        model_config.provider,
        model_config.model_name,
        workspace,
    )
    logging.getLogger(__name__).info(
        "[任务] API容错：空闲超时%d秒，单次总上限%d秒，请求最多%d次，格式修正最多%d次",
        model_config.timeout_seconds,
        model_config.max_wall_time_seconds,
        model_config.request_attempts,
        model_config.parse_attempts,
    )
    logging.getLogger(__name__).info(
        "[任务] 模型采样：temperature=%g，top_p=%s；探索思考=%s，求解思考=%s",
        model_config.temperature,
        model_config.top_p if model_config.top_p is not None else "provider-default",
        model_config.reasoning_effort,
        model_config.solve_reasoning_effort,
    )
    logging.getLogger(__name__).info(
        "[独立成功审计] 模式=%s；provider/model=%s/%s；每题最多%d个有效审计；"
        "同一候选最多一次格式修正，总客户端调用最多为有效审计上限的2倍；"
        "模型自报task_success仅作诊断",
        args.success_judge_mode,
        judge_config.provider if judge_config is not None else "off",
        judge_config.model_name if judge_config is not None else "off",
        args.success_judge_max_calls,
    )
    if (
        judge_config is not None
        and judge_config.provider == model_config.provider
        and judge_config.model_name == model_config.model_name
    ):
        logging.getLogger(__name__).warning(
            "[独立成功审计] 当前与求解器使用同一模型，只实现上下文隔离；"
            "正式对照实验建议配置不同模型或服务商"
        )
    logging.getLogger(__name__).info(
        "[预算] 复杂度=%s；基础=%d轮/%d次工具，初始=%d轮/%d次工具；"
        "弹性续算=%s，硬上限=%d轮/%d次工具；依据=%s",
        budget_level,
        args.max_iterations,
        args.max_tool_calls,
        adjusted_iterations,
        adjusted_tool_calls,
        "关闭" if mcts_config.budget_multiplier == 1 else "开启",
        math.ceil(adjusted_iterations * mcts_config.budget_multiplier),
        math.ceil(adjusted_tool_calls * mcts_config.budget_multiplier),
        "、".join(budget_reasons),
    )
    logging.getLogger(__name__).info(
        "[搜索] Selection模式=%s；hybrid回根间隔=%d轮；"
        "语义树宽=%d..%d；语义等价节点合并=%s",
        mcts_config.selection_mode,
        mcts_config.hybrid_root_interval,
        mcts_config.base_children_per_node,
        mcts_config.max_children_per_node,
        mcts_config.semantic_node_merge,
    )

    try:
        result = TaskRunner(
            environment=environment,
            policy=policy,
            mcts_config=mcts_config,
            checkpoint_path=checkpoint_path,
            success_judge=success_judge,
        ).run(task)
    except (OSError, RuntimeError, ValueError) as error:
        #已有检查点时仍把最佳工作区写到标准输出，让benchmark可以继续运行verifier
        if checkpoint_path.is_file():
            try:
                fallback = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                saved_success = bool(fallback.get("succeeded"))
                fallback["succeeded"] = saved_success
                fallback["verified_success"] = saved_success
                fallback.setdefault(
                    "search_algorithm",
                    "phase_adaptive_semantic_best_first",
                )
                fallback.setdefault(
                    "interaction_rounds",
                    fallback.get("transitions_completed", 0),
                )
                fallback["stop_reason"] = (
                    "verified_success_preserved_after_runtime_error"
                    if saved_success
                    else "runtime_error_with_checkpoint"
                )
                fallback["error"] = str(error).replace("\r", " ").replace("\n", " ")[:240]
                fallback["model_usage"] = policy.model_usage_summary()
                fallback["success_judge_usage"] = (
                    success_judge.usage_summary() if success_judge is not None else {}
                )
                fallback["run_root"] = str(run_root.resolve())
                print(json.dumps(fallback, ensure_ascii=False, indent=2, default=list))
                logging.getLogger(__name__).error(
                    "[任务] 运行异常，已输出最近检查点：%s",
                    fallback["error"],
                )
                return 0 if saved_success else 1
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                pass
        parser.exit(2, f"运行失败: {error}\n")

    output = {
        "task_id": task.task_id,
        "succeeded": result.succeeded,
        "verified_success": result.verified_success,
        "model_task_success_claimed": any(
            item.assessment.task_success for item in result.transitions
        ),
        "model_task_success_claim_count": sum(
            1 for item in result.transitions if item.assessment.task_success
        ),
        "candidate_success_count": sum(
            1 for item in result.transitions if item.assessment.candidate_success
        ),
        "stop_reason": result.stop_reason,
        "interaction_rounds": result.interaction_rounds,
        "scheduling_trace": result.scheduling_trace,
        "base_children_per_node": mcts_config.base_children_per_node,
        "max_children_per_node": mcts_config.max_children_per_node,
        "frontier_max_entries_per_direction": (
            mcts_config.frontier_max_entries_per_direction
        ),
        "frontier_stale_after_iterations": (
            mcts_config.frontier_stale_after_iterations
        ),
        "frontier_stale_min_attempts": mcts_config.frontier_stale_min_attempts,
        "effective_iteration_budget": result.effective_iteration_budget,
        "effective_tool_call_budget": result.effective_tool_call_budget,
        "hard_iteration_budget": result.hard_iteration_budget,
        "hard_tool_call_budget": result.hard_tool_call_budget,
        "total_tool_calls": result.total_tool_calls,
        "reserved_final_verification_tool_calls": (
            result.reserved_final_verification_tool_calls
        ),
        "final_verification_tool_calls": result.final_verification_tool_calls,
        "search_algorithm": result.search_algorithm,
        "model_usage": policy.model_usage_summary(),
        "success_judge_mode": result.success_judge_mode,
        "success_judge_provider": (
            judge_config.provider if judge_config is not None else "off"
        ),
        "success_judge_model": (
            judge_config.model_name if judge_config is not None else "off"
        ),
        "success_judge_calls": result.success_judge_calls,
        "success_judge_usage": result.success_judge_usage,
        "success_judge_decisions": result.success_judge_decisions,
        "semantic_coverage_rate": result.post_hoc_indicators.final_semantic_coverage_rate,
        "core_semantic_coverage_rate": (
            result.post_hoc_indicators.final_semantic_coverage_rate
        ),
        "discovered_semantic_coverage_rate": semantic_coverage_rate(
            result.best_node.context
        ),
        "post_hoc_indicators": asdict(result.post_hoc_indicators),
        "grpo_samples": [asdict(sample) for sample in result.grpo_samples],
        "best_context": result.best_node.context.to_dict(),
        "best_workspace": result.best_node.snapshot.location,
        "task_rules": [asdict(rule) for rule in result.rules],
        "run_root": str(run_root.resolve()),
        "checkpoint_path": str(checkpoint_path.resolve()),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=list))
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
