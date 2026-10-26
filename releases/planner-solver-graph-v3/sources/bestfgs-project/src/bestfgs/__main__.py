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
from .best_first_runtime import BestFGSConfig, adapt_search_budget
from .environment import EnvironmentConfig, ForkedWorkspaceEnvironment
from .models import TaskSpec
from .retrac_adapter import (
    RetracModelConfig,
    RetracPolicyAdapter,
    OpenAICompatibleJSONClient,
)
from .semantic import semantic_coverage_rate
from .cli_config import model_config_from_args
from .collaboration import build_collaborative_policy
from .experiment_metrics import ExperimentRecorder


GRAPH_RUNTIME_VERSION = "branching-graph-v14"


#真实模型的最小启动入口，不包含实验编排、批量评测和跨任务记忆
def build_parser() -> argparse.ArgumentParser:
    defaults = BestFGSConfig()
    parser = argparse.ArgumentParser(
        description="v13任务内经验智能体；默认恢复全局语义BestFGS图搜索，evidence保留顺序控制器供消融"
    )
    parser.add_argument("--engine", choices=("graph", "evidence", "legacy"), default="graph",
                        help="graph为v13默认全局语义BestFGS图搜索；evidence为顺序证据控制器；legacy是graph兼容别名")
    parser.add_argument("--blocking-memory", choices=("off", "advisory", "control"), default="off",
                        help="顺序evidence引擎的阻塞记忆；graph保留原有分支方式并要求off")
    parser.add_argument("--disable-evidence-branching", action="store_true",
                        help="关闭显式快照回退，保留顺序解题与经验，供消融实验")
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
    parser.add_argument("--comparison-metrics", action="store_true", help="Record method-independent CLI comparison metrics (adds file hashing overhead)")

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
        "--experience-mode",
        choices=("off", "legacy", "conditioned"),
        default="conditioned",
        help="任务经验控制：off关闭额外经验，legacy保留旧规则，conditioned按条件和实测证据复用（默认）",
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
        choices=("off",),
        default="off",
        help="独立LLM结果审计已撤下；保留off参数兼容旧启动命令",
    )
    parser.add_argument(
        "--success-judge-provider",
        choices=("openai", "deepseek", "dashscope"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--success-judge-model",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--success-judge-base-url",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--success-judge-api-key-env",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--success-judge-max-calls",
        type=int,
        default=3,
        help=argparse.SUPPRESS,
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

    if args.engine == "evidence":
        from .evidence_runtime import run_from_args
        return run_from_args(args, parser)
    if args.blocking_memory != "off":
        parser.error("graph/legacy engine preserves the original BestFGS branching controller; use --blocking-memory off")

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
        model_config = model_config_from_args(args)
        best_fgs_config = BestFGSConfig(
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
            rule_candidate_limit=args.rule_candidate_limit,
            experience_mode=args.experience_mode,
            post_success_iterations=args.post_success_iterations,
            require_successful_verification=(
                not args.allow_unverified_success
            ),
            success_judge_mode=args.success_judge_mode,
            base_children_per_node=args.base_children_per_node,
            max_children_per_node=args.max_children_per_node,
            frontier_max_entries_per_direction=args.frontier_max_per_direction,
            frontier_stale_after_iterations=args.frontier_stale_after_iterations,
            frontier_stale_min_attempts=args.frontier_stale_min_attempts,
            semantic_node_merge=not args.disable_semantic_node_merge,
            semantic_merge_fact_threshold=args.semantic_merge_fact_threshold,
            semantic_merge_issue_threshold=args.semantic_merge_issue_threshold,
        )
        best_fgs_config.validate()
    except ValueError as error:
        parser.error(str(error))

    task = TaskSpec.create(
        args.goal,
        success_criteria=tuple(args.success_criterion) or (args.goal,),
        constraints=tuple(args.constraint),
    )
    run_root = (args.run_root or Path(tempfile.gettempdir()) / "bestfgs" / task.task_id)
    checkpoint_path = run_root / "search_checkpoint.json"
    recorder = ExperimentRecorder(run_root / "cli-metrics.jsonl") if args.comparison_metrics else None
    environment = ForkedWorkspaceEnvironment(
        seed_workspace=workspace,
        run_root=run_root,
        config=EnvironmentConfig(),
        allowed_executables=set(args.allow_executable) if args.allow_executable else None,
        recorder=recorder,
    )
    policy = build_collaborative_policy(model_config,
        diagnostics_dir=run_root, experience_mode=args.experience_mode)
    success_judge = None
    judge_config = None
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
        "[结果判定] 显式只读提交与公开验证；task_success/覆盖率不能结束任务；官方结果由外部评测填写",
    )
    logging.getLogger(__name__).info(
        "[预算] 复杂度=%s；基础=%d轮/%d次工具，初始=%d轮/%d次工具；"
        "弹性续算=%s，硬上限=%d轮/%d次工具；依据=%s",
        budget_level,
        args.max_iterations,
        args.max_tool_calls,
        adjusted_iterations,
        adjusted_tool_calls,
        "关闭" if best_fgs_config.budget_multiplier == 1 else "开启",
        math.ceil(adjusted_iterations * best_fgs_config.budget_multiplier),
        math.ceil(adjusted_tool_calls * best_fgs_config.budget_multiplier),
        "、".join(budget_reasons),
    )
    logging.getLogger(__name__).info(
        "[搜索] 算法=阶段自适应语义Best-First；"
        "语义动作容量=%d..%d；语义等价节点合并=%s",
        best_fgs_config.base_children_per_node,
        best_fgs_config.max_children_per_node,
        best_fgs_config.semantic_node_merge,
    )

    try:
        result = TaskRunner(
            environment=environment,
            policy=policy,
            config=best_fgs_config,
            checkpoint_path=checkpoint_path,
            success_judge=success_judge,
        ).run(task)
    except (OSError, RuntimeError, ValueError) as error:
        #已有检查点时仍把最佳工作区写到标准输出，让benchmark可以继续运行verifier
        if checkpoint_path.is_file():
            try:
                fallback = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                # An interrupted checkpoint is a rescued artifact, never an
                # official success (nor a completed final submission).
                fallback["succeeded"] = False
                fallback["verified_success"] = False
                fallback["submitted"] = False
                fallback["official_resolved"] = None
                if isinstance(fallback.get("delivery"), dict):
                    fallback["delivery"].update(
                        submitted=False, official_resolved=None,
                        status="draft" if fallback["delivery"].get("has_patch") else "empty",
                    )
                fallback.setdefault(
                    "search_algorithm",
                    "phase_adaptive_semantic_best_first",
                )
                fallback.setdefault(
                    "interaction_rounds",
                    fallback.get("transitions_completed", 0),
                )
                fallback["stop_reason"] = "runtime_error_with_checkpoint"
                fallback.setdefault("experience_mode", best_fgs_config.experience_mode)
                fallback.setdefault("experience_report", {})
                fallback["error"] = str(error).replace("\r", " ").replace("\n", " ")[:240]
                fallback["model_usage"] = policy.model_usage_summary()
                if recorder:
                    fallback["comparison_metrics"] = recorder.summary()
                fallback["success_judge_usage"] = (
                    success_judge.usage_summary() if success_judge is not None else {}
                )
                fallback["run_root"] = str(run_root.resolve())
                print(json.dumps(fallback, ensure_ascii=False, indent=2, default=list))
                logging.getLogger(__name__).error(
                    "[任务] 运行异常，已输出最近检查点：%s",
                    fallback["error"],
                )
                return 1
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                pass
        parser.exit(2, f"运行失败: {error}\n")

    output = {
        "runtime_version": GRAPH_RUNTIME_VERSION,
        "task_id": task.task_id,
        "succeeded": result.succeeded,
        "verified_success": result.verified_success,
        "submitted": result.submitted,
        "local_validation_passed": result.delivery.get("local_validation_passed", False),
        "official_resolved": None,
        "delivery": result.delivery,
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
        "search_efficiency": result.search_efficiency,
        "experience_mode": result.experience_mode,
        "experience_report": result.experience_report,
        "task_experiences": result.task_experiences,
        "base_children_per_node": best_fgs_config.base_children_per_node,
        "max_children_per_node": best_fgs_config.max_children_per_node,
        "frontier_max_entries_per_direction": (
            best_fgs_config.frontier_max_entries_per_direction
        ),
        "frontier_stale_after_iterations": (
            best_fgs_config.frontier_stale_after_iterations
        ),
        "frontier_stale_min_attempts": best_fgs_config.frontier_stale_min_attempts,
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
        "branching_enabled": True,
        "blocking_memory_mode": "off",
        "decision_turns": result.interaction_rounds,
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
    if recorder:
        output["comparison_metrics"] = recorder.summary()
    print(json.dumps(output, ensure_ascii=False, indent=2, default=list))
    # Exit 0 means a normally finished run with a deliverable, not resolved.
    return 0 if result.delivery.get("has_patch") else 1


if __name__ == "__main__":
    from .lean_cli import main as lean_main
    raise SystemExit(lean_main())
