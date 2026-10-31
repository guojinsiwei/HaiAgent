from __future__ import annotations

import json
import math
import logging
import re
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Literal, Protocol

from .environment import CLIEnvironment
from .metrics import PostHocIndicatorAnalyzer, PostHocIndicatorReport
from .models import (
    CommandResult,
    CommandSpec,
    ExecutionOutcome,
    InitialSemanticPlan,
    MacroAction,
    ModelCallError,
    RewardBreakdown,
    SearchEdge,
    SearchGraph,
    SearchNode,
    SemanticDirection,
    StructuredContext,
    TaskSpec,
    TransitionAssessment,
    TransitionRecord,
    TransitionUpdate,
    stable_id,
)
from .rl import GRPOBuffer, GRPOSample
from .rules import FailureKind, RuleScope, TaskRule, TaskRuleStore
from .semantic import (
    SemanticNodeMergeConfig,
    TaskKnowledgeBoard,
    bind_transition_evidence,
    invalidate_context_for_workspace_changes,
    merge_semantically_equivalent_contexts,
    merge_semantic_directions,
    merge_verified_facts,
    register_action_directions,
    semantic_coverage_rate,
    semantic_coverage_snapshot,
    set_direction_status,
    snapshot_changed_paths_from_root,
)
from .success_judge import (
    SuccessJudge,
    SuccessJudgeDecision,
    unavailable_decision,
)

"""BestFGS 的独立运行时。

本模块拥有 Agent 的搜索生命周期、预算、快照转移、任务内知识、候选管理与
最终复验。具体的全局前沿选择由 ``SemanticBestFirstGraphSearch`` 实现。
"""
logger = logging.getLogger(__name__)

'''参数配置 '''
# BestFGS运行配置：控制语义动作容量、前沿、预算、候选与验证生命周期。
@dataclass(slots=True)
class BestFGSConfig:
    max_iterations: int = 24
    initial_branching_factor: int = 3
    expansion_width: int = 3
    max_expansion_batches_per_node: int = 1
    max_commands_per_macro_action: int = 4
    max_total_tool_calls: int = 80
    #从总工具预算中预留至多两组宏动作容量，用于最终候选复验。
    #小预算单元测试/消融（少于12次）不启用预留，避免预算失去可执行意义。
    verification_reserve_ratio: float = 0.10
    verification_reserve_max_tool_calls: int = 8
    late_stage_remaining_iterations: int = 2
    semantic_coverage_switch_threshold: float = 0.48
    # 平滑求解压力达到该值，或已经出现成熟候选时进入求解模式。
    solve_mode_pressure_threshold: float = 0.20
    rule_candidate_limit: int = 5
    #保留旧构造参数名以兼容实验脚本；它现在控制的是verified_success终止。
    stop_on_task_success: bool = True
    post_success_iterations: int = 0
    require_successful_verification: bool = True
    #off保留旧的确定性门槛；audit只记录独立判定；required要求独立判定PASS。
    success_judge_mode: Literal["off", "audit", "required"] = "off"
    # 3是无额外证据时的基础宽度；未解决的语义需求可以把容量提高到6。
    # 该容量不读取节点访问次数，不属于progressive widening。
    base_children_per_node: int = 3
    max_children_per_node: int = 6
    # BestFGS全局前沿软剪枝：图节点不会删除，只限制当前轮可被选中的候选。
    frontier_max_entries_per_direction: int = 2
    frontier_stale_after_iterations: int = 4
    frontier_stale_min_attempts: int = 2
    # 1.0保持严格预算；CLI和benchmark入口默认传4.0，在初始预算耗尽后
    # 分段续算，直到verified_success、搜索耗尽或达到硬上限。
    budget_multiplier: float = 1.0
    semantic_node_merge: bool = True
    semantic_merge_fact_threshold: float = 0.90
    semantic_merge_issue_threshold: float = 0.80

    @property
    def stop_on_verified_success(self) -> bool:
        return self.stop_on_task_success

    def validate(self) -> None:
        for name in (
            "max_iterations",
            "initial_branching_factor",
            "expansion_width",
            "max_expansion_batches_per_node",
            "max_commands_per_macro_action",
            "max_total_tool_calls",
            "verification_reserve_max_tool_calls",
            "late_stage_remaining_iterations",
            "rule_candidate_limit",
            "base_children_per_node",
            "max_children_per_node",
            "frontier_max_entries_per_direction",
            "frontier_stale_after_iterations",
            "frontier_stale_min_attempts",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.base_children_per_node > self.max_children_per_node:
            raise ValueError(
                "base_children_per_node must not exceed max_children_per_node"
            )
        if not 0.0 <= self.verification_reserve_ratio <= 0.5:
            raise ValueError("verification_reserve_ratio must be in [0, 0.5]")
        if not math.isfinite(self.budget_multiplier) or self.budget_multiplier < 1:
            raise ValueError("budget_multiplier must be finite and at least 1")
        if not 0 < self.semantic_coverage_switch_threshold <= 1:
            raise ValueError("semantic_coverage_switch_threshold must be in (0, 1]")
        if not 0 < self.solve_mode_pressure_threshold <= 1:
            raise ValueError("solve_mode_pressure_threshold must be in (0, 1]")
        if self.post_success_iterations < 0:
            raise ValueError("post_success_iterations must be non-negative")
        if self.success_judge_mode not in {"off", "audit", "required"}:
            raise ValueError("success_judge_mode must be off, audit, or required")
        for name in (
            "semantic_merge_fact_threshold",
            "semantic_merge_issue_threshold",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

''' 先根据题目难度做资源调度（预算）'''
@dataclass(frozen=True, slots=True)
class TaskBudgetDecision:
    """题面结构复杂度只调度运行预算，不属于研究指标或在线奖励。"""

    complexity: Literal["simple", "standard", "complex"]
    max_iterations: int
    max_total_tool_calls: int
    reasons: tuple[str, ...]


def adapt_search_budget(
    task_text: str,
    *,
    base_iterations: int,
    base_tool_calls: int,
) -> TaskBudgetDecision:
    """用题面结构作保守三级调度，不调用额外模型，也不读取参考答案。"""
    if base_iterations <= 0 or base_tool_calls <= 0:
        raise ValueError("base search budgets must be positive")
    text = task_text.strip()
    nonempty_lines = tuple(line for line in text.splitlines() if line.strip())
    file_refs = set(
        re.findall(
            r"(?:[A-Za-z0-9_.-]+[/\\])+[A-Za-z0-9_.-]+|"
            r"\b[A-Za-z0-9_-]+\.(?:py|js|ts|java|c|cc|cpp|h|go|rs|sh|yaml|yml|toml)\b",
            text,
        )
    )
    requirement_lines = sum(
        1
        for line in nonempty_lines
        if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line)
    )
    score = 0
    reasons: list[str] = []
    if len(text) >= 1600:
        score += 2
        reasons.append("long problem statement")
    elif len(text) >= 800:
        score += 1
        reasons.append("moderately long problem statement")
    elif len(text) <= 350:
        score -= 1
        reasons.append("short problem statement")
    if len(nonempty_lines) >= 25:
        score += 1
        reasons.append("many non-empty lines")
    if len(file_refs) >= 3:
        score += 1
        reasons.append("multiple referenced files")
    if requirement_lines >= 4:
        score += 1
        reasons.append("multiple explicit requirements")
    if "```" in text or "Traceback (most recent call last)" in text:
        score += 1
        reasons.append("embedded code or traceback")

    if score <= 0:
        complexity: Literal["simple", "standard", "complex"] = "simple"
        scale = 0.9
    elif score >= 3:
        complexity = "complex"
        scale = 1.35
    else:
        complexity = "standard"
        scale = 1.0
    return TaskBudgetDecision(
        complexity=complexity,
        max_iterations=max(4, math.ceil(base_iterations * scale)),
        max_total_tool_calls=max(12, math.ceil(base_tool_calls * scale)),
        reasons=tuple(reasons) or ("ordinary statement structure",),
    )


#在线奖励配置与搜索配置分离，方便强化学习实验单独调整奖励尺度
@dataclass(slots=True)
class RewardConfig:
    semantic_coverage_delta_weight: float = 1.0
    task_success_reward: float = 1.0

'''
当前在线奖励只有：
语义覆盖率增量 + 任务成功奖励
'''
#在线奖励只使用语义覆盖率增量和外部任务成功反馈
@dataclass(frozen=True, slots=True)
class TransitionRewardCalculator:
    config: RewardConfig

    def calculate(
        self,
        *,
        semantic_coverage_before: float,
        semantic_coverage_after: float,
        verified_success: bool,
    ) -> RewardBreakdown:
        delta = semantic_coverage_after - semantic_coverage_before
        coverage_reward = self.config.semantic_coverage_delta_weight * delta
        terminal_reward = (
            self.config.task_success_reward if verified_success else 0.0
        )
        return RewardBreakdown(
            total=coverage_reward + terminal_reward,
            semantic_coverage_delta=coverage_reward,
            task_success_reward=terminal_reward,
        )

'''
模型接口的要求
'''
#完整策略接口：根节点生成Bootstrap首动作，普通节点执行Expansion，并用一次请求更新真实转移
class PolicyModel(Protocol):
    def propose_initial_skeleton(
        self,
        *,
        task: TaskSpec,
        context: StructuredContext,
        rules: tuple[TaskRule, ...],
        limit: int,
        budget_status: dict[str, int | str] | None = None,
    ) -> tuple[MacroAction, ...]: ...

    def propose_actions(
        self,
        *,
        task: TaskSpec,
        context: StructuredContext,
        rules: tuple[TaskRule, ...],
        limit: int,
        solve_mode: bool = False,
        budget_status: dict[str, int | str] | None = None,
    ) -> tuple[MacroAction, ...]: ...

    def update_transition(
        self,
        *,
        task: TaskSpec,
        previous: StructuredContext,
        action: MacroAction,
        outcome: ExecutionOutcome,
    ) -> TransitionUpdate: ...


#完整搜索结果：保留搜索图、任务规则、事后指标以及结构化GRPO样本
@dataclass(frozen=True, slots=True)
class SearchResult:
    task: TaskSpec
    graph: SearchGraph
    transitions: tuple[TransitionRecord, ...]
    rules: tuple[TaskRule, ...]
    post_hoc_indicators: PostHocIndicatorReport
    grpo_samples: tuple[GRPOSample, ...]
    best_node_id: str
    stop_reason: str
    total_tool_calls: int
    scheduling_trace: tuple[dict, ...] = ()
    effective_iteration_budget: int = 0
    effective_tool_call_budget: int = 0
    hard_iteration_budget: int = 0
    hard_tool_call_budget: int = 0
    final_verification_tool_calls: int = 0
    reserved_final_verification_tool_calls: int = 0
    success_judge_mode: str = "off"
    success_judge_calls: int = 0
    success_judge_usage: dict[str, int | float] = field(default_factory=dict)
    success_judge_decisions: tuple[dict, ...] = ()
    search_algorithm: str = "phase_adaptive_semantic_best_first"

    @property
    def verified_success(self) -> bool:
        return self.stop_reason == "verified_success"

    @property
    def succeeded(self) -> bool:
        return self.verified_success

    @property
    def interaction_rounds(self) -> int:
        """Count real environment transitions; model retries are reported separately."""

        return len(self.transitions)

    @property
    def best_node(self) -> SearchNode:
        return self.graph.nodes[self.best_node_id]


# BestFGS公共生命周期；在线前沿策略由具体算法实现。
class BestFirstSearchRuntime:
    """BestFGS-owned lifecycle with pluggable graph-frontier selection.

    The runtime owns the BestFGS lifecycle while the concrete search class
    implements global frontier selection.
    """
    def __init__(
        self,
        *,
        environment: CLIEnvironment,
        policy: PolicyModel,
        rule_store: TaskRuleStore,
        config: BestFGSConfig | None = None,
        reward_config: RewardConfig | None = None,
        checkpoint_path: Path | None = None,
        success_judge: SuccessJudge | None = None,
    ) -> None:
        self.environment = environment
        self.policy = policy
        self.rule_store = rule_store
        self.config = config or BestFGSConfig()
        self.config.validate()
        self.reward_calculator = TransitionRewardCalculator(reward_config or RewardConfig())
        self.checkpoint_path = checkpoint_path
        self.success_judge = success_judge
        self._model_failure_count = 0
        self._knowledge_board: TaskKnowledgeBoard | None = None
        self._solve_mode = False
        self._experience_ready = False
        self._scheduling_trace: list[dict] = []
        self._fallback_candidate_node_id: str | None = None
        self._incumbent_candidate_node_id: str | None = None
        self._verified_candidate_node_ids: list[str] = []
        self._candidate_verification_commands: dict[
            str, tuple[CommandSpec, ...]
        ] = {}
        self._incumbent_verified_success_node_id: str | None = None
        self._finalized_node_id: str | None = None
        self._runtime_iteration = 0
        self._runtime_active_iteration_budget = self.config.max_iterations
        self._runtime_total_tool_calls = 0
        self._runtime_active_tool_budget = self.config.max_total_tool_calls
        self._runtime_hard_tool_budget = self.config.max_total_tool_calls
        self._verification_reserve_tool_calls = 0
        self._final_verification_budget = 0
        self._final_verification_tool_calls = 0
        self._budget_planning_blocked = False
        self._success_judge_decisions: list[dict] = []
        self._experience_events: dict[str, int] = {}
        self._experience_event_keys: set[tuple[str, ...]] = set()

    def _reset_experience_events(self) -> None:
        self._experience_events = {}
        self._experience_event_keys = set()

    def _count_experience(self, name: str, amount: int = 1) -> None:
        if not hasattr(self, "_experience_events"):
            self._experience_events = {}
        self._experience_events[name] = self._experience_events.get(name, 0) + amount

    def _count_experience_once(self, name: str, *parts: str) -> None:
        if not hasattr(self, "_experience_event_keys"):
            self._experience_event_keys = set()
        key = (name, *parts)
        if key in self._experience_event_keys:
            return
        self._experience_event_keys.add(key)
        self._count_experience(name)

    def _core_direction_ids(self) -> frozenset[str]:
        knowledge_board = getattr(self, "_knowledge_board", None)
        if knowledge_board is None:
            return frozenset()
        return knowledge_board.core_direction_ids

    def _core_coverage_rate(self, context: StructuredContext) -> float:
        core_ids = self._core_direction_ids()
        return semantic_coverage_rate(
            context,
            direction_ids=core_ids or None,
        )

    def _judge_candidate(
        self,
        *,
        task: TaskSpec,
        action: MacroAction,
        outcome: ExecutionOutcome,
    ) -> SuccessJudgeDecision:
        if self.success_judge is None:
            decision = unavailable_decision("no success judge configured")
        else:
            try:
                decision = self.success_judge.evaluate(
                    task=task,
                    action=action,
                    outcome=outcome,
                )
            except ModelCallError as error:
                decision = unavailable_decision(str(error))
        payload = decision.to_dict()
        payload.update(
            {
                "iteration": self._runtime_iteration,
                "action_name": action.name,
                "snapshot_fingerprint": outcome.resulting_snapshot.fingerprint,
            }
        )
        self._success_judge_decisions.append(payload)
        return decision

    def _success_judge_usage(self) -> dict[str, int | float]:
        if self.success_judge is None:
            return {}
        usage = getattr(self.success_judge, "usage_summary", None)
        return usage() if callable(usage) else {}

    def _compute_verification_reserve(self, hard_tool_budget: int) -> int:
        if hard_tool_budget < 12 or self.config.verification_reserve_ratio <= 0:
            return 0
        requested = math.ceil(
            hard_tool_budget * self.config.verification_reserve_ratio
        )
        return min(
            self.config.verification_reserve_max_tool_calls,
            max(1, requested),
            hard_tool_budget - 1,
        )

    def _set_runtime_budget_state(
        self,
        *,
        iteration: int,
        active_iteration_budget: int,
        total_tool_calls: int,
        active_tool_budget: int,
        hard_tool_budget: int,
    ) -> None:
        self._runtime_iteration = iteration
        self._runtime_active_iteration_budget = active_iteration_budget
        self._runtime_total_tool_calls = total_tool_calls
        self._runtime_active_tool_budget = active_tool_budget
        self._runtime_hard_tool_budget = hard_tool_budget

    def _planning_budget_status(self) -> dict[str, int | str]:
        current_iteration = getattr(self, "_runtime_iteration", 0)
        active_iteration_budget = getattr(
            self,
            "_runtime_active_iteration_budget",
            self.config.max_iterations,
        )
        total_tool_calls = getattr(self, "_runtime_total_tool_calls", 0)
        active_tool_budget = getattr(
            self,
            "_runtime_active_tool_budget",
            self.config.max_total_tool_calls,
        )
        hard_tool_budget = getattr(
            self,
            "_runtime_hard_tool_budget",
            active_tool_budget,
        )
        verification_reserve = getattr(
            self,
            "_verification_reserve_tool_calls",
            0,
        )
        remaining_iterations = max(
            0,
            active_iteration_budget - max(1, current_iteration) + 1,
        )
        if current_iteration == 0:
            remaining_iterations = active_iteration_budget
        remaining_total_calls = max(
            0,
            active_tool_budget - total_tool_calls,
        )
        remaining_action_calls = max(
            0,
            remaining_total_calls - verification_reserve,
        )
        next_action_capacity = max(
            0,
            hard_tool_budget - total_tool_calls - verification_reserve,
        )
        urgency = "normal"
        if remaining_action_calls <= 0:
            urgency = "verification_reserve"
        elif (
            remaining_iterations <= self.config.late_stage_remaining_iterations
            or remaining_action_calls <= self.config.max_commands_per_macro_action * 2
        ):
            urgency = "closing"
        return {
            "current_iteration": current_iteration,
            "active_iteration_budget": active_iteration_budget,
            "remaining_iterations": remaining_iterations,
            "used_tool_calls": total_tool_calls,
            "active_tool_call_budget": active_tool_budget,
            "hard_tool_call_budget": hard_tool_budget,
            "remaining_total_tool_calls": remaining_total_calls,
            "reserved_final_verification_tool_calls": verification_reserve,
            "remaining_action_tool_calls": remaining_action_calls,
            "maximum_commands_for_next_action": min(
                self.config.max_commands_per_macro_action,
                next_action_capacity,
            ),
            "urgency": urgency,
            "search_phase": "solve" if self._solve_mode else "explore",
        }

    '''建立根节点，然后重复“选节点—选动作—执行—更新状态—建边—回传”，直到成功或预算耗尽。 '''
    def search(self, *, task: TaskSpec, initial_context: StructuredContext) -> SearchResult:
        if task.task_id != self.rule_store.task_id:
            raise ValueError("the rule store must belong to the current task")
        #初始化
        graph = SearchGraph()
        root = graph.add_root(initial_context, self.environment.initial_snapshot())
        #knowledge_board共享只读事实和语义地图；TaskRuleStore另外共享带作用域的
        #成功/失败试错经验，二者都只存在于当前任务生命周期内。
        self._knowledge_board = TaskKnowledgeBoard.create(
            root.snapshot.fingerprint,
            initial_context,
        )
        self._solve_mode = False
        self._experience_ready = False
        self._scheduling_trace = []
        self._fallback_candidate_node_id = None
        self._incumbent_candidate_node_id = None
        self._verified_candidate_node_ids = []
        self._candidate_verification_commands = {}
        self._incumbent_verified_success_node_id = None
        self._finalized_node_id = None
        self._budget_planning_blocked = False
        self._success_judge_decisions = []
        self._reset_experience_events()
        #transitions：所有真实状态转移记录。
        transitions: list[TransitionRecord] = []
        grpo = GRPOBuffer()
        total_tool_calls = 0
        stop_reason = "iteration_budget_exhausted"
        first_verified_success_iteration: int | None = None
        active_iteration_budget = self.config.max_iterations
        active_tool_budget = self.config.max_total_tool_calls
        hard_iteration_budget = max(
            active_iteration_budget,
            math.ceil(active_iteration_budget * self.config.budget_multiplier),
        )
        hard_tool_budget = max(
            active_tool_budget,
            math.ceil(active_tool_budget * self.config.budget_multiplier),
        )
        self._verification_reserve_tool_calls = self._compute_verification_reserve(
            hard_tool_budget
        )
        self._final_verification_tool_calls = 0
        self._set_runtime_budget_state(
            iteration=0,
            active_iteration_budget=active_iteration_budget,
            total_tool_calls=total_tool_calls,
            active_tool_budget=active_tool_budget,
            hard_tool_budget=hard_tool_budget,
        )
        iteration_extension = max(4, math.ceil(self.config.max_iterations / 2))
        tool_extension = max(12, math.ceil(self.config.max_total_tool_calls / 2))
        logger.info(
            "[SearchCore] 开始任务：初始%d轮/%d次工具；成功导向硬上限%d轮/%d次工具",
            active_iteration_budget, active_tool_budget,
            hard_iteration_budget, hard_tool_budget,
        )
        if self._verification_reserve_tool_calls:
            logger.info(
                "[预算感知] 总工具预算中预留%d次用于最终候选复验",
                self._verification_reserve_tool_calls,
            )
        #模型先定义稳定的语义覆盖空间，但不把方向直接建成多条搜索边；同一次
        #规划只接纳一个Bootstrap动作，真实反馈形成经验后再进行探索优先Expansion。
        logger.info(
            "[SearchCore] 初始规划：先建立语义地图，再执行1个Bootstrap动作积累经验"
        )
        self._populate_actions(graph, root, task, initial=True)
        '''
        一轮搜索只选择一个 MacroAction。
          这里得到两个重要结果：
          node           本轮从哪个节点继续
          selected_path  根节点到这个节点经过的边
          路径留下来是为了最后Backpropagation。
        '''
        iteration = 1
        while iteration <= active_iteration_budget:
            action_tool_ceiling = max(
                0,
                active_tool_budget - self._verification_reserve_tool_calls,
            )
            if total_tool_calls >= action_tool_ceiling:
                if active_tool_budget < hard_tool_budget:
                    old_tool_budget = active_tool_budget
                    active_tool_budget = min(
                        hard_tool_budget, active_tool_budget + tool_extension
                    )
                    if active_iteration_budget < hard_iteration_budget:
                        active_iteration_budget = min(
                            hard_iteration_budget,
                            active_iteration_budget + iteration_extension,
                        )
                    logger.info(
                        "[弹性预算] 尚未verified_success：工具预算%d→%d，轮次预算现为%d/%d",
                        old_tool_budget, active_tool_budget,
                        active_iteration_budget, hard_iteration_budget,
                    )
                else:
                    stop_reason = (
                        "verification_reserve_reached"
                        if self._verification_reserve_tool_calls
                        else (
                            "hard_tool_call_budget_exhausted"
                            if self.config.budget_multiplier > 1
                            else "tool_call_budget_exhausted"
                        )
                    )
                    logger.info(
                        "[预算感知] 普通动作额度已耗尽，停止新探索并进入最终候选复验"
                    )
                    break
            self._set_runtime_budget_state(
                iteration=iteration,
                active_iteration_budget=active_iteration_budget,
                total_tool_calls=total_tool_calls,
                active_tool_budget=active_tool_budget,
                hard_tool_budget=hard_tool_budget,
            )
            logger.info(
                "[SearchCore] 迭代 %d/%d（硬上限%d），已使用工具调用 %d/%d（硬上限%d）",
                iteration,
                active_iteration_budget,
                hard_iteration_budget,
                total_tool_calls,
                active_tool_budget,
                hard_tool_budget,
            )

            self._maybe_activate_solve_mode(graph, iteration, task=task)

            node, selected_path = self._select(graph, task, iteration=iteration)
            if node is None:
                stop_reason = (
                    "verification_reserve_reached"
                    if self._budget_planning_blocked
                    else (
                        "model_unavailable"
                        if self._model_failure_count and not transitions
                        else "search_exhausted"
                    )
                )
                logger.info("[SearchCore] 没有可继续探索的节点，提前结束搜索")
                break
            action = self._take_pending_action(
                node,
                max_tool_calls=int(
                    self._planning_budget_status()["maximum_commands_for_next_action"]
                ),
            )
            if action is None:
                stop_reason = (
                    "verification_reserve_reached"
                    if self._verification_reserve_tool_calls and node.pending_actions
                    else "search_exhausted"
                )
                logger.info(
                    "[SearchCore] 当前搜索图没有符合剩余预算的新动作，提前结束搜索"
                )
                break
            phase = (
                "initial_exploration" if not self._solve_mode
                else "recommend_exploitation" if action.applied_rule_ids
                else "candidate_refinement" if action.intent == "candidate"
                else "focused_fallback_exploration"
            )
            decision = {
                "iteration": iteration,
                "node_id": node.node_id,
                "phase": phase,
                "action_name": action.name,
                "recommend_rule_ids": list(action.applied_rule_ids),
                "avoid_rule_ids": list(action.avoided_rule_ids),
                "active_child_limit": self._active_child_limit(node),
                "budget_status": self._planning_budget_status(),
            }
            trace_hook = getattr(self, "_decision_trace_fields", None)
            if callable(trace_hook):
                decision.update(trace_hook(node, action))
            logger.info(
                "[调度] %s；当前/最大树宽=%d/%d；有效recommend=%d；有效avoid规避=%d",
                phase, decision["active_child_limit"],
                self.config.max_children_per_node, len(action.applied_rule_ids),
                len(action.avoided_rule_ids),
            )
            #核心覆盖率使用初始冻结分母，参与阶段切换和在线奖励；动态发现
            #覆盖率保留运行中新方向，作为诊断指标单独记录。
            coverage_before = self._core_coverage_rate(node.context)
            discovered_coverage_before = semantic_coverage_rate(node.context)
            requested_calls = min(
                len(action.commands) + len(action.verification_commands),
                self.config.max_commands_per_macro_action,
            )
            if (
                requested_calls
                > active_tool_budget
                - total_tool_calls
                - self._verification_reserve_tool_calls
                and active_tool_budget < hard_tool_budget
            ):
                old_tool_budget = active_tool_budget
                active_tool_budget = min(
                    hard_tool_budget,
                    max(active_tool_budget + tool_extension, total_tool_calls + requested_calls),
                )
                logger.info(
                    "[弹性预算] 为完整执行本轮动作及验证，工具预算%d→%d",
                    old_tool_budget, active_tool_budget,
                )
            self._set_runtime_budget_state(
                iteration=iteration,
                active_iteration_budget=active_iteration_budget,
                total_tool_calls=total_tool_calls,
                active_tool_budget=active_tool_budget,
                hard_tool_budget=hard_tool_budget,
            )
            remaining_calls = max(
                0,
                active_tool_budget
                - total_tool_calls
                - self._verification_reserve_tool_calls,
            )
            if requested_calls > remaining_calls:
                stop_reason = "verification_reserve_reached"
                logger.info(
                    "[预算感知] 动作需要%d次调用、普通动作额度仅剩%d次；"
                    "保留复验预算并停止新动作",
                    requested_calls,
                    remaining_calls,
                )
                break
            logger.info(
                "[SearchCore] 选择动作：%s；语义方向：%s；包含%d条命令",
                action.name,
                action.semantic_direction_label,
                min(
                    requested_calls,
                    remaining_calls,
                ),
            )
            outcome = self.environment.execute(
                node.snapshot,
                action,
                min(self.config.max_commands_per_macro_action, remaining_calls),
            )
            total_tool_calls += outcome.tool_call_count
            self._set_runtime_budget_state(
                iteration=iteration,
                active_iteration_budget=active_iteration_budget,
                total_tool_calls=total_tool_calls,
                active_tool_budget=active_tool_budget,
                hard_tool_budget=hard_tool_budget,
            )
            self._experience_ready = True
            self._scheduling_trace.append(decision)
            logger.info(
                "[SearchCore] CLI执行结束：%d条命令，全部成功=%s",
                outcome.tool_call_count,
                outcome.commands_succeeded,
            )
            ''' 
            execution_gate_passed =
            普通命令成功
            and 自动语法检查成功
           '''
            #成功命令照常评估；求解阶段的失败命令也交给模型读取stderr，
            #让下一轮能够针对真实错误修复，而不是只得到一条通用失败摘要。
            execution_gate_passed = (
                outcome.commands_succeeded and outcome.validation_succeeded
            )
            functional_validation_failed = (
                outcome.functional_validation_attempted
                and not outcome.functional_validation_succeeded
            )
            changed_paths = outcome.changed_workspace_paths
            valid_previous = invalidate_context_for_workspace_changes(
                node.context,
                changed_paths,
            )
            prior_statuses = {
                item.direction_id: item.status
                for item in node.context.semantic_directions
            }
            reopened_direction_ids = frozenset(
                item.direction_id
                for item in valid_previous.semantic_directions
                if item.status == "unexplored"
                and prior_statuses.get(item.direction_id) == "covered"
            )
            if valid_previous != node.context:
                logger.info(
                    "[证据有效性] 工作区变化使%d个语义方向需要重新验证；变化路径=%s",
                    len(reopened_direction_ids),
                    ", ".join(changed_paths[:6]),
                )
            should_model_update = execution_gate_passed or self._solve_mode
            """
            模型阅读stdout和stderr，返回：
                  assessment
                  ├─ 语义方向状态
                  ├─ 模型是否认为完成任务
                  ├─ 本轮证据支持的成功标准
                  └─ 解释反馈
                  next_context
                  └─ 压缩后的新上下文
            但是模型不能直接生成verified_success。程序会另外检查：
                必须是candidate动作
                必须修改了工作区
                普通命令和语法门槛必须通过
                功能验证命令必须通过
                任务定义中的全部成功标准必须有证据覆盖
            """
            if should_model_update:
                try:
                    update = self.policy.update_transition(
                        task=task,
                        previous=valid_previous,
                        action=action,
                        outcome=outcome,
                    )
                    assessment = update.assessment
                    compressed = update.next_context
                    if not execution_gate_passed or (
                        action.intent == "candidate" and functional_validation_failed
                    ):
                        assessment = replace(assessment, direction_status="failed")
                        logger.info(
                            "[SearchCore] 求解阶段执行、基础门槛或候选功能验证失败；"
                            "模型已分析真实错误输出"
                        )
                except ModelCallError as error:
                    #模型暂时不可用时仍保留真实观测；失败CLI不能伪装成探索进展
                    self._model_failure_count += 1
                    assessment = TransitionAssessment(
                        direction_status=(
                            "exploring" if execution_gate_passed else "failed"
                        ),
                        task_success=False,
                        feedback=(
                            _model_failure_transition_feedback(outcome)
                            if execution_gate_passed
                            else _failed_transition_feedback(outcome)
                        ),
                    )
                    compressed = replace(
                        valid_previous,
                        environment_summary=outcome.resulting_snapshot.summary,
                    )
                    logger.warning(
                        "[SearchCore] 转移模型不可用，已保留真实快照并继续：%s",
                        _safe_model_error(error),
                    )
            else:
                #探索阶段保持快速失败路径，避免为普通路径或工具错误额外调用模型
                assessment = TransitionAssessment(
                    direction_status="failed",
                    task_success=False,
                    feedback=_failed_transition_feedback(outcome),
                )
                compressed = replace(
                    valid_previous,
                    environment_summary=outcome.resulting_snapshot.summary,
                )
                logger.info("[SearchCore] 探索阶段CLI转移失败，跳过模型评估与上下文压缩")
            required_success_criteria = frozenset(task.required_success_criteria)
            satisfied_success_criteria = frozenset(
                assessment.satisfied_success_criteria
            )
            all_success_criteria_satisfied = required_success_criteria.issubset(
                satisfied_success_criteria
            )
            candidate_success = (
                action.intent == "candidate"
                and outcome.resulting_snapshot.fingerprint != graph.root().snapshot.fingerprint
                and execution_gate_passed
                and outcome.functional_validation_succeeded
                and assessment.direction_status != "failed"
            )
            judge_decision: SuccessJudgeDecision | None = None
            if candidate_success and self.config.success_judge_mode != "off":
                judge_decision = self._judge_candidate(
                    task=task,
                    action=action,
                    outcome=replace(outcome, audit_baseline_snapshot=graph.root().snapshot),
                )
                logger.info(
                    "[独立成功审计] verdict=%s；regression_risk=%s；%s",
                    judge_decision.verdict,
                    judge_decision.regression_risk,
                    judge_decision.summary,
                )
                judge_feedback_items = list(judge_decision.missing_checks)
                judge_feedback_items.extend(
                    f"Criterion '{item.criterion}': {item.reason}"
                    for item in judge_decision.criteria
                    if item.status != "satisfied"
                )
                judge_feedback_items.extend(
                    f"Risk '{item.risk_id}': {item.reason}"
                    for item in judge_decision.risk_checks
                    if item.status != "mitigated"
                )
                if (
                    not judge_feedback_items
                    and not judge_decision.passed
                    and judge_decision.audit_status == "evaluated"
                ):
                    judge_feedback_items.append(judge_decision.summary)
                if judge_feedback_items and judge_decision.audit_status == "evaluated":
                    gaps = tuple(
                        f"Independent verification gap: {item}"
                        for item in dict.fromkeys(judge_feedback_items[:6])
                    )
                    existing_direction_ids = {
                        item.direction_id for item in compressed.semantic_directions
                    }
                    gap_directions = tuple(
                        SemanticDirection(
                            stable_id(
                                "verify_direction",
                                {"task": task.task_id, "gap": gap.casefold()},
                            ),
                            gap[:160],
                        )
                        for gap in gaps
                        if stable_id(
                            "verify_direction",
                            {"task": task.task_id, "gap": gap.casefold()},
                        )
                        not in existing_direction_ids
                    )
                    compressed = replace(
                        compressed,
                        unresolved_issues=tuple(
                            dict.fromkeys((*compressed.unresolved_issues, *gaps))
                        ),
                        incomplete_plans=tuple(
                            dict.fromkeys((*compressed.incomplete_plans, *gaps))
                        ),
                        semantic_directions=(
                            *compressed.semantic_directions,
                            *gap_directions,
                        ),
                    )

            legacy_verified_success = (
                candidate_success and all_success_criteria_satisfied
            )
            if not self.config.require_successful_verification:
                verified_success = assessment.task_success
            elif self.config.success_judge_mode == "required":
                verified_success = bool(
                    candidate_success
                    and judge_decision is not None
                    and judge_decision.passed
                )
            else:
                #off保持测试/兼容入口原语义；audit记录Judge但不改变停止结果。
                verified_success = legacy_verified_success
            if assessment.task_success and not verified_success:
                rejection_reasons: list[str] = []
                if not candidate_success:
                    rejection_reasons.append("候选修改或独立功能验证门槛未通过")
                if (
                    self.config.success_judge_mode != "required"
                    and not all_success_criteria_satisfied
                ):
                    missing = required_success_criteria.difference(
                        satisfied_success_criteria
                    )
                    rejection_reasons.append(
                        "未覆盖成功标准=" + " | ".join(sorted(missing))
                    )
                if (
                    self.config.success_judge_mode == "required"
                    and judge_decision is not None
                    and not judge_decision.passed
                ):
                    rejection_reasons.append(
                        "独立审计=" + judge_decision.verdict
                    )
                assessment = replace(
                    assessment,
                    feedback=(
                        assessment.feedback
                        + "；task_success仅为模型声明，verified_success=false："
                        + "；".join(rejection_reasons)
                    ),
                )
                logger.info(
                    "[验证] 模型声明task_success，但运行时未生成verified_success"
                )
            elif verified_success and not assessment.task_success:
                verification_note = (
                    "运行时硬门槛与独立证据审计通过，生成verified_success"
                    if self.config.success_judge_mode == "required"
                    else "运行时根据完整成功标准覆盖与独立功能验证生成verified_success"
                )
                assessment = replace(
                    assessment,
                    feedback=(
                        assessment.feedback
                        + "；" + verification_note
                    ),
                )
                logger.info(
                    "[验证] 模型task_success为false，但独立证据审计与运行时门槛完整；"
                    "生成verified_success"
                )
            assessment = replace(
                assessment,
                candidate_success=candidate_success,
                judge_verdict=(
                    (judge_decision.verdict if judge_decision.audit_status == "evaluated"
                     else "unavailable") if judge_decision is not None else "off"
                ),
                judge_summary=(
                    judge_decision.summary if judge_decision is not None else ""
                ),
                verified_success=verified_success,
            )
            logger.info(
                "[SearchCore] 转移评估：方向状态=%s，模型task_success=%s，"
                "模型声称标准覆盖=%d/%d，candidate_success=%s，Judge=%s，"
                "verified_success=%s",
                assessment.direction_status,
                assessment.task_success,
                len(required_success_criteria.intersection(satisfied_success_criteria)),
                len(required_success_criteria),
                assessment.candidate_success,
                assessment.judge_verdict,
                assessment.verified_success,
            )
            """
            模型压缩以后，程序进行四次修正：
            merge_verified_facts()父节点验证过的事实不能遗忘。
            merge_semantic_directions()已经登记的语义方向不能丢失。
            set_direction_status()更新本轮探索方向的状态。
            knowledge_board.enrich()加入任务内共享的只读事实。
            """
            #模型负责压缩，程序负责把父路径上已经验证的事实确定性传给子节点
            compressed, action_dependencies = bind_transition_evidence(
                valid_previous,
                compressed,
                outcome,
                semantic_direction_id=action.semantic_direction_id,
            )
            next_context = merge_verified_facts(
                valid_previous,
                compressed,
                semantic_direction_id=action.semantic_direction_id,
            )
            next_context = merge_semantic_directions(valid_previous, next_context)
            #模型只能用本轮真实观测重新覆盖当前动作对应的方向，不能把其他
            #刚因文件变化而失效的方向在压缩输出中直接改回covered。
            if reopened_direction_ids:
                next_context = replace(
                    next_context,
                    semantic_directions=tuple(
                        replace(
                            item,
                            status="unexplored",
                            workspace_dependencies=(),
                            observed_at_fingerprint="",
                        )
                        if item.direction_id in reopened_direction_ids
                        else item
                        for item in next_context.semantic_directions
                    ),
                )
            next_context = set_direction_status(
                next_context,
                direction_id=action.semantic_direction_id,
                label=action.semantic_direction_label,
                status=assessment.direction_status,
                evidence=assessment.feedback,
                workspace_dependencies=action_dependencies,
                observed_at_fingerprint=outcome.resulting_snapshot.fingerprint,
            )
            if self._knowledge_board is not None:
                shared = self._knowledge_board.absorb_read_only_transition(
                    next_context,
                    outcome,
                )
                promoted_directions = (
                    self._knowledge_board.promote_supported_candidates((next_context,))
                )
                next_context = self._knowledge_board.enrich(
                    next_context,
                    changed_paths_from_root=snapshot_changed_paths_from_root(
                        outcome.resulting_snapshot,
                        self._knowledge_board.root_fingerprint,
                    ),
                )
                if promoted_directions:
                    logger.info(
                        "[语义地图] 新事实或未决问题支持%d个候选方向，已升级为正式方向",
                        len(promoted_directions),
                    )
                if shared:
                    logger.info(
                        "[知识板] 已共享初始工作区上的验证事实；全局语义覆盖率=%.1f%%",
                        self._knowledge_board.semantic_coverage_rate() * 100,
                    )
            #计算奖励：动态发现新方向不会扩大核心分母，只有核心方向证据
            #新增或失效才改变在线覆盖奖励。
            coverage_after = self._core_coverage_rate(next_context)
            discovered_coverage_after = semantic_coverage_rate(next_context)
            reward = self.reward_calculator.calculate(
                semantic_coverage_before=coverage_before,
                semantic_coverage_after=coverage_after,
                verified_success=assessment.verified_success,
            )
            core_before_counts = semantic_coverage_snapshot(
                node.context,
                direction_ids=self._core_direction_ids(),
            )
            core_after_counts = semantic_coverage_snapshot(
                next_context,
                direction_ids=self._core_direction_ids(),
            )
            discovered_before_counts = semantic_coverage_snapshot(node.context)
            discovered_after_counts = semantic_coverage_snapshot(next_context)
            logger.info(
                "[SearchCore] 核心语义覆盖率%d/%d(%.1f%%) -> %d/%d(%.1f%%)；"
                "动态发现覆盖率%d/%d(%.1f%%) -> %d/%d(%.1f%%)；"
                "新增正式方向=%d，重开方向=%d，本轮奖励=%.3f",
                core_before_counts.covered,
                core_before_counts.total,
                coverage_before * 100,
                core_after_counts.covered,
                core_after_counts.total,
                coverage_after * 100,
                discovered_before_counts.covered,
                discovered_before_counts.total,
                discovered_coverage_before * 100,
                discovered_after_counts.covered,
                discovered_after_counts.total,
                discovered_coverage_after * 100,
                len(promoted_directions) if self._knowledge_board is not None else 0,
                len(reopened_direction_ids),
                reward.total,
            )
            #增加/合并节点
            child, edge, merged = graph.add_or_merge_child(
                parent=node,
                context=next_context,
                snapshot=outcome.resulting_snapshot,
                action=action,
                terminal=assessment.verified_success,
                semantic_coverage_rate=coverage_after,
                applicable_rule_ids=(
                    *action.applied_rule_ids,
                    *action.avoided_rule_ids,
                ),
                context_merger=(
                    self._merge_equivalent_contexts
                    if self.config.semantic_node_merge
                    else None
                ),
            )
            if merged:
                logger.info(
                    "[SearchCore] 当前转移复用了同环境下的等价搜索节点：%s",
                    child.node_id,
                )
            workspace_usable = execution_gate_passed and (
                outcome.workspace_changed
                or (action.intent == "candidate" and outcome.resulting_snapshot.fingerprint
                    != graph.root().snapshot.fingerprint)
            )
            if outcome.workspace_changed and not workspace_usable:
                logger.info("[SearchCore] 当前修改基础门槛失败，保留上一工作分支")

            if action.intent == "candidate" and workspace_usable:
                if (
                    outcome.functional_validation_succeeded
                    and assessment.direction_status != "failed"
                ):
                    self._fallback_candidate_node_id = child.node_id
                    self._register_verified_candidate(
                        graph,
                        child,
                        action.verification_commands,
                    )
                elif not outcome.functional_validation_attempted:
                    # 预算不足等原因导致验证根本未执行时，可保留首个明确候选作
                    # 最后兜底；已经明确验证失败的候选不能覆盖更好的旧候选。
                    if self._fallback_candidate_node_id is None:
                        self._fallback_candidate_node_id = child.node_id
                    logger.info(
                        "[候选解] 功能验证未执行，保留为可继续修复的未验证候选"
                    )
                else:
                    logger.info(
                        "[候选解] 功能验证失败，仅作为工作分支继续修复，不覆盖旧候选"
                    )
            #保存完整轨迹
            transition = TransitionRecord(
                task_id=task.task_id,
                iteration=iteration,
                parent_node_id=node.node_id,
                child_node_id=child.node_id,
                action=action,
                outcome=outcome,
                assessment=assessment,
                reward=reward,
                state_before=node.context,
                state_after=next_context,
                semantic_coverage_before=coverage_before,
                semantic_coverage_after=coverage_after,
                discovered_semantic_coverage_before=discovered_coverage_before,
                discovered_semantic_coverage_after=discovered_coverage_after,
            )
            transitions.append(transition)
            grpo.add_transition(transition)
            self._distill_rule(task, transition)
            #Backpropagation
            self._write_checkpoint(
                task=task,
                graph=graph,
                transitions=transitions,
                total_tool_calls=total_tool_calls,
                stop_reason="running",
            )
            if (self.config.success_judge_mode == "required"
                    and judge_decision is not None and not judge_decision.passed
                    and (judge_decision.audit_status != "evaluated"
                         or getattr(self.success_judge, "budget_exhausted", False))):
                # Judge 是额外的提前成功门槛，不是搜索预算。服务不可用或
                # 审计额度耗尽时，保留当前候选并继续用剩余交互修复/验证；
                # 只有真正 PASS 才允许 verified_success 提前终止。
                audit_state = (
                    "judge_budget_exhausted"
                    if getattr(self.success_judge, "budget_exhausted", False)
                    or judge_decision.audit_status == "budget_exhausted"
                    else "judge_unavailable"
                )
                logger.warning(
                    "[独立成功审计] %s；仅关闭提前成功通道，搜索继续到正常预算/前沿终点",
                    audit_state,
                )
            #若成功，先保存好成功节点，并将剩余轮次用于寻找更好的解答
            if assessment.verified_success:
                if self._incumbent_verified_success_node_id is None:
                    first_verified_success_iteration = iteration
                    self._incumbent_verified_success_node_id = child.node_id
                    if self.config.post_success_iterations:
                        logger.info(
                            "[SearchCore] 已保存首个经独立验证的成功节点%s；"
                            "继续探索最多%d轮寻找更优解",
                            child.node_id,
                            self.config.post_success_iterations,
                        )
                    else:
                        logger.info(
                            "[SearchCore] 节点%s已通过独立验证；立即结束当前任务",
                            child.node_id,
                        )
                else:
                    incumbent = graph.nodes[self._incumbent_verified_success_node_id]
                    if _successful_node_key(child) > _successful_node_key(incumbent):
                        self._incumbent_verified_success_node_id = child.node_id
                        logger.info("[SearchCore] 已用更优成功节点更新保底解：%s", child.node_id)
                stop_reason = "verified_success"
                if (
                    self.config.stop_on_verified_success
                    and first_verified_success_iteration is not None
                    and iteration
                    >= first_verified_success_iteration + self.config.post_success_iterations
                ):
                    logger.info("[SearchCore] 已满足验证成功终止条件")
                    break

            if iteration >= active_iteration_budget and first_verified_success_iteration is None:
                if active_iteration_budget < hard_iteration_budget:
                    old_iteration_budget = active_iteration_budget
                    active_iteration_budget = min(
                        hard_iteration_budget,
                        active_iteration_budget + iteration_extension,
                    )
                    active_tool_budget = min(
                        hard_tool_budget,
                        active_tool_budget + tool_extension,
                    )
                    logger.info(
                        "[弹性预算] 尚未verified_success：轮次预算%d→%d，工具预算现为%d/%d",
                        old_iteration_budget, active_iteration_budget,
                        active_tool_budget, hard_tool_budget,
                    )
                elif self.config.budget_multiplier > 1:
                    stop_reason = "hard_iteration_budget_exhausted"
            iteration += 1

        if first_verified_success_iteration is not None:
            #后续探索即使耗尽或没有新动作，也不能覆盖已经保存的成功状态。
            stop_reason = "verified_success"

        #事后指标和经验漏斗只在完整任务轨迹形成后计算
        post_hoc = PostHocIndicatorAnalyzer.analyze(
            transitions,
            experience_events=self._experience_events,
        )
        self._final_verification_budget = max(
            0,
            active_tool_budget - total_tool_calls,
        )
        best = self._finalize_best_node(graph)
        total_tool_calls += self._final_verification_tool_calls
        if stop_reason == "verified_success" and not best.terminal:
            stop_reason = "final_verification_failed"
        self._write_checkpoint(
            task=task,
            graph=graph,
            transitions=transitions,
            total_tool_calls=total_tool_calls,
            stop_reason=stop_reason,
        )
        logger.info(
            "[SearchCore] 搜索结束：原因=%s，完成%d次有效转移，工具调用%d次",
            stop_reason,
            len(transitions),
            total_tool_calls,
        )
        judge_usage = self._success_judge_usage()
        return SearchResult(
            task=task,
            graph=graph,
            transitions=tuple(transitions),
            rules=self.rule_store.all(),
            post_hoc_indicators=post_hoc,
            grpo_samples=grpo.with_group_relative_advantages(),
            best_node_id=best.node_id,
            stop_reason=stop_reason,
            total_tool_calls=total_tool_calls,
            scheduling_trace=tuple(self._scheduling_trace),
            effective_iteration_budget=active_iteration_budget,
            effective_tool_call_budget=active_tool_budget,
            hard_iteration_budget=hard_iteration_budget,
            hard_tool_call_budget=hard_tool_budget,
            final_verification_tool_calls=self._final_verification_tool_calls,
            reserved_final_verification_tool_calls=(
                self._verification_reserve_tool_calls
            ),
            success_judge_mode=self.config.success_judge_mode,
            success_judge_calls=int(judge_usage.get("judge_calls", 0)),
            success_judge_usage=judge_usage,
            success_judge_decisions=tuple(self._success_judge_decisions),
            search_algorithm=self.search_algorithm,
        )

    # 具体算法必须决定从全图选哪个状态。BestFGS 在 best_first.py 中实现
    # 全局前沿由 best_first.py 实现。
    def _select(
        self,
        graph: SearchGraph,
        task: TaskSpec,
        *,
        iteration: int,
    ) -> tuple[SearchNode | None, list[SearchEdge]]:
        raise NotImplementedError("a graph search policy must implement _select")
    def _can_expand_node(self, node: SearchNode) -> bool:
        """语义压力决定基础值到硬上限之间的容量（默认3到6），不读取访问次数。"""

        action_signatures = set(node.tried_action_ids)
        action_signatures.update(action.signature() for action in node.pending_actions)
        active_child_limit = self._active_child_limit(node)
        if len(action_signatures) >= active_child_limit:
            return False
        batch_limit = max(
            self.config.max_expansion_batches_per_node,
            active_child_limit,
        )
        return node.expansion_batches < batch_limit

    def _active_child_limit(self, node: SearchNode) -> int:
        """把尚未解决的不同语义需求映射成当前节点容量，范围为base..max。"""

        open_direction_ids = {
            item.direction_id
            for item in node.context.semantic_directions
            if item.status != "covered"
        }
        base = self.config.base_children_per_node
        # 一旦形成成熟候选，宽度收回基础值，把预算留给修复与验证；已经
        # 建出的边不会删除。没有候选时才根据独立语义方向和前沿不确定性扩宽。
        mature_candidate = bool(
            getattr(self, "_incumbent_candidate_node_id", None)
            or getattr(self, "_fallback_candidate_node_id", None)
            or getattr(self, "_has_mature_candidate_evidence", lambda: False)()
        )
        if mature_candidate:
            return base
        semantic_bonus = math.ceil(max(0, len(open_direction_ids) - base) / 2)
        uncertainty_hook = getattr(self, "_adaptive_width_bonus", None)
        uncertainty_bonus = (
            max(0, int(uncertainty_hook(node))) if callable(uncertainty_hook) else 0
        )
        return min(
            self.config.max_children_per_node,
            max(base, base + semantic_bonus + uncertainty_bonus),
        )


    # 作用：根据当前求解阶段和Selection模式，判断本轮是否从最近的连续工作节点开始搜索。

    # 作用：用广度优先搜索重建根节点到指定节点的一条最短路径，供完整奖励回传使用。
    @staticmethod
    def _path_from_root(
        graph: SearchGraph,
        target_node_id: str,
    ) -> list[SearchEdge] | None:
        """在搜索图中重建一条根到目标的最短边路径，供完整回传使用。"""

        root_id = graph.root().node_id
        if target_node_id == root_id:
            return []
        queue: deque[tuple[str, list[SearchEdge]]] = deque([(root_id, [])])
        seen = {root_id}
        while queue:
            node_id, path = queue.popleft()
            node = graph.nodes[node_id]
            for edge_id in node.outgoing_edge_ids:
                edge = graph.edges[edge_id]
                if edge.target_node_id == target_node_id:
                    return [*path, edge]
                if edge.target_node_id in seen:
                    continue
                seen.add(edge.target_node_id)
                queue.append((edge.target_node_id, [*path, edge]))
        return None

    # 作用：优先恢复产生当前工作节点的真实路径；记录失效时再从搜索图中重新寻找路径。

    def _capacity_action_ids(self, node: SearchNode) -> set[str]:
        return set(node.tried_action_ids) | {a.signature() for a in node.pending_actions}

    # 作用：为节点生成候选动作，结合任务规则完成过滤、去重和排序后放入待执行队列。
    def _populate_actions(
        self,
        graph: SearchGraph,
        node: SearchNode,
        task: TaskSpec,
        *,
        initial: bool,
    ) -> None:
        self._sync_node_knowledge(graph, node)
        budget_status = self._planning_budget_status()
        maximum_commands = int(budget_status["maximum_commands_for_next_action"])
        if maximum_commands <= 0:
            self._budget_planning_blocked = True
            logger.info("[预算感知] 已无普通动作额度，跳过新的模型规划请求")
            return
        if (
            self._solve_mode
            and self._verification_reserve_tool_calls
            and maximum_commands < 2
        ):
            self._budget_planning_blocked = True
            logger.info(
                "[预算感知] 剩余额度不足以同时完成候选修改和独立验证，"
                "跳过新的求解模型请求"
            )
            return
        candidate_rules = self.rule_store.retrieve(
            task_id=task.task_id,
            context=node.context,
            limit=self.config.rule_candidate_limit,
            environment_fingerprint=node.snapshot.fingerprint,
        )
        if self.rule_store.all():
            logger.info(
                "[规则] 从当前任务%d条规则中召回%d条候选",
                len(self.rule_store.all()),
                len(candidate_rules),
            )
        logger.info(
            "[经验引导] 当前Expansion读取%d条recommend、%d条avoid；"
            "节点动作容量%d/%d",
            sum(rule.kind == "recommend" for rule in candidate_rules),
            sum(rule.kind == "avoid" for rule in candidate_rules),
            len(node.tried_action_ids) + len(node.pending_actions),
            self._active_child_limit(node),
        )
        limit = (
            self.config.initial_branching_factor
            if initial
            else self.config.expansion_width
        )
        known = set(node.tried_action_ids)
        known.update(item.signature() for item in node.pending_actions)
        active_child_limit = self._active_child_limit(node)
        remaining_capacity = active_child_limit - len(self._capacity_action_ids(node))
        if budget_status["urgency"] == "closing":
            remaining_capacity = min(remaining_capacity, 1)
        if remaining_capacity <= 0:
            return
        planning_context = node.context
        if not initial and self._knowledge_board is not None:
            planning_context = self._knowledge_board.enrich_for_planning(node.context)
        # 这里才是真正把规则交给规划模型，因此“召回/暴露”只在模型请求
        # 即将发生时计数，不把内部容量检查伪装成经验复用。
        self._count_experience("retrieval_events")
        self._count_experience(
            "recommend_rules_exposed",
            sum(rule.kind == "recommend" for rule in candidate_rules),
        )
        self._count_experience(
            "avoid_rules_exposed",
            sum(rule.kind == "avoid" for rule in candidate_rules),
        )
        self._count_experience(
            "semantic_avoid_exposures",
            sum(
                rule.kind == "avoid" and rule.scope == "semantic_strategy"
                for rule in candidate_rules
            ),
        )
        initial_directions: tuple[SemanticDirection, ...] = ()
        try:
            if initial:
                planner = getattr(self.policy, "propose_initial_plan", None)
                if callable(planner):
                    plan = planner(
                        task=task,
                        context=planning_context,
                        rules=candidate_rules,
                        limit=limit,
                        budget_status=budget_status,
                    )
                    if not isinstance(plan, InitialSemanticPlan):
                        raise TypeError(
                            "propose_initial_plan must return InitialSemanticPlan"
                        )
                    initial_directions = plan.semantic_directions
                    proposed = (plan.bootstrap_action,)
                else:
                    proposed = self.policy.propose_initial_skeleton(
                        task=task,
                        context=planning_context,
                        rules=candidate_rules,
                        limit=limit,
                        budget_status=budget_status,
                    )
                    # 兼容尚未实现语义计划接口的轻量策略：旧候选同时提供
                    # 语义地图，但只有排序第一的动作获得 Bootstrap 执行资格。
                    direction_by_id: dict[str, SemanticDirection] = {}
                    for action in proposed:
                        direction_by_id.setdefault(
                            action.semantic_direction_id,
                            SemanticDirection(
                                action.semantic_direction_id,
                                action.semantic_direction_label,
                            ),
                        )
                    initial_directions = tuple(direction_by_id.values())
            else:
                proposed = self.policy.propose_actions(
                    task=task,
                    context=planning_context,
                    rules=candidate_rules,
                    limit=limit,
                    solve_mode=self._solve_mode,
                    budget_status=budget_status,
                )
        except ModelCallError as error:
            #一个节点的Expansion失败不能让已经完成的其他搜索分支全部丢失
            self._model_failure_count += 1
            node.expansion_batches += 1
            logger.warning(
                "[SearchCore] %s模型不可用，跳过当前节点：%s",
                "Bootstrap动作" if initial else "节点扩展",
                _safe_model_error(error),
            )
            return
        node.applicable_rule_ids = tuple(rule.rule_id for rule in candidate_rules)

        known = set(node.tried_action_ids)
        known.update(item.signature() for item in node.pending_actions)
        # 初期沿用Explore每次接纳一个动作、先扩展再沿已有边选择的方式。
        # 求解阶段可暂存同批候选供recommend优先调度；容量由当前语义需求决定。
        acceptance_limit = min(limit, remaining_capacity)
        if initial:
            acceptance_limit = 1
        covered_directions = {
            item.direction_id
            for item in node.context.semantic_directions
            if item.status == "covered"
        }
        accepted = 0
        accepted_actions: list[MacroAction] = []
        blocked_candidates: list[tuple[int, MacroAction, tuple[str, ...]]] = []
        valid_candidates: list[MacroAction] = []
        for proposal_index, action in enumerate(proposed):
            if action.semantic_direction_id in covered_directions:
                logger.info(
                    "[SearchCore] 跳过动作%s：语义方向%s已经覆盖",
                    action.name,
                    action.semantic_direction_label,
                )
                continue
            self._count_experience("actions_evaluated_against_rules")
            if action.applied_rule_ids or action.avoided_rule_ids:
                self._count_experience("model_rule_selected_actions")
            rule_application = self.rule_store.evaluate(
                task_id=task.task_id,
                action=action,
                environment_fingerprint=node.snapshot.fingerprint,
            )
            recommended = rule_application.recommend_rule_ids
            avoided = rule_application.avoided_rule_ids
            if rule_application.blocked:
                self._count_experience_once(
                    "avoid_actions_blocked",
                    node.node_id,
                    node.snapshot.fingerprint,
                    action.signature(),
                )
                logger.info("[规则] 跳过动作%s：适用的avoid规则已阻止该动作", action.name)
                if action.signature() not in known:
                    blocked_candidates.append((proposal_index, action, recommended))
                continue
            if action.signature() in known:
                continue
            # 两种经验使用独立字段：Recommend推动复用，Avoid证明当前动作
            # 采用了不同于失败轨迹的替代方案。两者都会进入在线优先级。
            action = replace(
                action,
                applied_rule_ids=recommended,
                avoided_rule_ids=avoided,
            )
            if recommended:
                self._count_experience_once(
                    "recommend_actions_validated",
                    node.node_id,
                    node.snapshot.fingerprint,
                    action.signature(),
                )
            if avoided:
                self._count_experience_once(
                    "avoid_actions_validated",
                    node.node_id,
                    node.snapshot.fingerprint,
                    action.signature(),
                )
            valid_candidates.append(action)
            known.add(action.signature())
        valid_candidates.sort(
            key=lambda action: (
                not bool(action.applied_rule_ids) if self._solve_mode else False,
                not bool(action.avoided_rule_ids),
            )
        )
        accepted_actions = valid_candidates[:acceptance_limit]
        for accepted_action in accepted_actions:
            if accepted_action.applied_rule_ids:
                self._count_experience_once(
                    "recommend_actions_enqueued",
                    node.node_id,
                    node.snapshot.fingerprint,
                    accepted_action.signature(),
                )
            if accepted_action.avoided_rule_ids:
                self._count_experience_once(
                    "avoid_actions_enqueued",
                    node.node_id,
                    node.snapshot.fingerprint,
                    accepted_action.signature(),
                )
        node.pending_actions.extend(accepted_actions)
        accepted = len(accepted_actions)

        # avoid是当前任务中归纳出的经验规则，不是环境安全策略。若它把本批所有
        # 可用动作都拦截，继续请求模型只会形成空转；此时按现有待选动作优先级
        # 保留一个候选。CLIEnvironment仍会校验危险程序、白名单和工作区边界。
        if accepted == 0 and blocked_candidates:
            proposal_index, fallback, recommended = max(
                blocked_candidates,
                key=lambda item: (
                    bool(item[2]),
                    len(item[2]),
                    -item[0],
                ),
            )
            # 被avoid阻止的经验性兜底不能冒充“可用recommend”。
            fallback = replace(
                fallback,
                applied_rule_ids=(),
                avoided_rule_ids=(),
            )
            node.pending_actions.append(fallback)
            accepted_actions.append(fallback)
            known.add(fallback.signature())
            accepted = 1
            self._count_experience("all_blocked_fallback_overrides")
            logger.warning(
                "[规则] 本批可用动作全部被经验性avoid规则阻止；"
                "回退保留动作%s（模型顺序%d），环境硬约束仍然生效",
                fallback.name,
                proposal_index + 1,
            )
        #初始语义地图只定义覆盖空间，不创建边；常规Expansion仍然只登记运行时
        #真正接纳的动作，避免未执行候选形成“幽灵方向”。
        accepted_tuple = tuple(accepted_actions)
        if self._knowledge_board is not None:
            if initial_directions:
                self._knowledge_board.register_directions(
                    initial_directions,
                    core=True,
                )
                logger.info(
                    "[语义地图] 已冻结%d个初始核心方向；后续发现仅进入动态覆盖",
                    len(self._knowledge_board.core_direction_ids),
                )
            self._knowledge_board.register_actions(accepted_tuple)
            promoted_directions = self._knowledge_board.defer_actions(
                proposed,
                accepted_tuple,
                node.context,
            )
            if promoted_directions:
                logger.info(
                    "[语义地图] %d个候选方向获得支持，已进入正式地图",
                    len(promoted_directions),
                )
            if self._knowledge_board.candidate_direction_count():
                logger.info(
                    "[语义地图] 候选池保留%d个暂未确认方向，不计入当前覆盖率",
                    self._knowledge_board.candidate_direction_count(),
                )
        registered = node.context
        if initial_directions:
            known_directions = {
                item.direction_id: item for item in registered.semantic_directions
            }
            for direction in initial_directions:
                known_directions.setdefault(direction.direction_id, direction)
            registered = replace(
                registered,
                semantic_directions=tuple(known_directions.values()),
            )
        registered = register_action_directions(registered, accepted_tuple)
        if self._knowledge_board is not None:
            registered = self._knowledge_board.enrich(
                registered,
                changed_paths_from_root=snapshot_changed_paths_from_root(
                    node.snapshot,
                    self._knowledge_board.root_fingerprint,
                ),
            )
        if registered != node.context:
            graph.update_context(node, registered)
        node.expansion_batches += 1
        logger.info(
            "[SearchCore] %s完成：模型提出%d个动作，规则过滤后接受%d个",
            "Bootstrap动作" if initial else "节点扩展",
            len(proposed),
            accepted,
        )

    # 作用：从节点的待执行队列中取出下一个动作，优先选择命中recommend规则的候选。
    def _take_pending_action(
        self,
        node: SearchNode,
        *,
        max_tool_calls: int | None = None,
    ) -> MacroAction | None:
        self._refresh_pending_actions(node)
        if not node.pending_actions:
            return None
        eligible_indices = [
            index
            for index, action in enumerate(node.pending_actions)
            if max_tool_calls is None
            or min(
                len(action.commands) + len(action.verification_commands),
                self.config.max_commands_per_macro_action,
            )
            <= max_tool_calls
        ]
        if not eligible_indices:
            return None
        best_index = max(
            eligible_indices,
            key=lambda index: (
                bool(node.pending_actions[index].applied_rule_ids),
                bool(node.pending_actions[index].avoided_rule_ids),
                getattr(self, "_solve_mode", False)
                and node.pending_actions[index].intent == "candidate",
                -index,
            ),
        )
        return node.pending_actions.pop(best_index)

    def _refresh_pending_actions(self, node: SearchNode) -> None:
        """执行前重验待选动作，防止旧ID、跨快照规则或新avoid造成假推荐。"""
        self._discard_globally_covered_actions(node)
        covered = {
            direction.direction_id for direction in node.context.semantic_directions
            if direction.status == "covered"
        }
        valid: list[MacroAction] = []
        blocked_actions: list[MacroAction] = []
        for action in node.pending_actions:
            if action.signature() in node.tried_action_ids or action.semantic_direction_id in covered:
                continue
            rule_application = self.rule_store.evaluate(
                task_id=self.rule_store.task_id,
                action=action,
                environment_fingerprint=node.snapshot.fingerprint,
            )
            recommended = rule_application.recommend_rule_ids
            avoided = rule_application.avoided_rule_ids
            if rule_application.blocked:
                self._count_experience_once(
                    "avoid_actions_blocked",
                    node.node_id,
                    node.snapshot.fingerprint,
                    action.signature(),
                )
                blocked_actions.append(replace(
                    action,
                    applied_rule_ids=(),
                    avoided_rule_ids=(),
                ))
            else:
                if recommended and not action.applied_rule_ids:
                    self._count_experience_once(
                        "recommend_actions_validated",
                        node.node_id,
                        node.snapshot.fingerprint,
                        action.signature(),
                    )
                    self._count_experience_once(
                        "recommend_actions_enqueued",
                        node.node_id,
                        node.snapshot.fingerprint,
                        action.signature(),
                    )
                if avoided and not action.avoided_rule_ids:
                    self._count_experience_once(
                        "avoid_actions_validated",
                        node.node_id,
                        node.snapshot.fingerprint,
                        action.signature(),
                    )
                    self._count_experience_once(
                        "avoid_actions_enqueued",
                        node.node_id,
                        node.snapshot.fingerprint,
                        action.signature(),
                    )
                valid.append(replace(
                    action,
                    applied_rule_ids=recommended,
                    avoided_rule_ids=avoided,
                ))
        # 沿用原实现的经验性avoid兜底，但它属于探索，不能获得推荐利用优先权。
        node.pending_actions[:] = valid or blocked_actions[:1]

    # 作用：把任务内共享的只读事实和语义状态同步到节点上下文，不修改节点对应的工作区快照。
    def _sync_node_knowledge(self, graph: SearchGraph, node: SearchNode) -> None:
        if self._knowledge_board is None:
            return
        enriched = self._knowledge_board.enrich(
            node.context,
            changed_paths_from_root=snapshot_changed_paths_from_root(
                node.snapshot,
                self._knowledge_board.root_fingerprint,
            ),
        )
        if enriched != node.context:
            graph.update_context(node, enriched)

    # 作用：删除语义方向已经被全局覆盖的待执行动作，避免不同分支重复探索同一事实。
    def _discard_globally_covered_actions(self, node: SearchNode) -> None:
        knowledge_board = getattr(self, "_knowledge_board", None)
        if knowledge_board is None:
            return
        covered = knowledge_board.covered_direction_ids(
            changed_paths_from_root=snapshot_changed_paths_from_root(
                node.snapshot,
                knowledge_board.root_fingerprint,
            )
        )
        if not covered:
            return
        node.pending_actions[:] = [
            action
            for action in node.pending_actions
            if action.semantic_direction_id not in covered
        ]

    # 作用：在覆盖率或轮次达到条件时切换到求解阶段，并清空探索阶段遗留的待执行动作。
    def _maybe_activate_solve_mode(
        self,
        graph: SearchGraph,
        iteration: int,
        *,
        task: TaskSpec | None = None,
    ) -> None:
        if self._solve_mode or self._knowledge_board is None:
            return
        budget_boundary = max(2, math.ceil(self.config.max_iterations / 4) + 1)
        budget_ready = self.config.max_iterations >= 6 and iteration >= budget_boundary
        coverage_ready = (
            self._knowledge_board.core_semantic_coverage_rate()
            >= self.config.semantic_coverage_switch_threshold
        )
        if not coverage_ready and not budget_ready:
            return
        promoted_directions = self._knowledge_board.audit_completeness(
            task_goal=task.goal if task is not None else graph.root().context.task_goal,
            success_criteria=task.success_criteria if task is not None else (),
            contexts=tuple(node.context for node in graph.nodes.values()),
        )
        if promoted_directions:
            for current in graph.nodes.values():
                enriched = self._knowledge_board.enrich(
                    current.context,
                    changed_paths_from_root=snapshot_changed_paths_from_root(
                        current.snapshot,
                        self._knowledge_board.root_fingerprint,
                    ),
                )
                if enriched != current.context:
                    graph.update_context(current, enriched)
            logger.info(
                "[语义地图] 求解前完整性审计补入%d个正式方向",
                len(promoted_directions),
            )
        self._solve_mode = True
        #旧待选动作来自探索阶段，清空后让模型基于共享事实重新生成求解动作；历史边和快照仍保留
        for node in graph.nodes.values():
            node.pending_actions.clear()
            node.expansion_batches = 0
            node.exhausted = False
        logger.info(
            "[SearchCore] 切换到求解阶段：固定核心语义覆盖率=%.1f%%；"
            "优先有效recommend，无推荐则探索替代修复；候选必须修改并验证",
            self._knowledge_board.core_semantic_coverage_rate() * 100,
        )

    # 旧树策略使用的可选扩展点；默认 BestFGS 前沿不调用它。

    # 作用：判断两个结构化上下文是否语义等价；等价且事实不冲突时返回合并后的上下文。
    def _merge_equivalent_contexts(
        self,
        left: StructuredContext,
        right: StructuredContext,
    ) -> StructuredContext | None:
        return merge_semantically_equivalent_contexts(
            left,
            right,
            config=SemanticNodeMergeConfig(
                verified_fact_similarity_threshold=(
                    self.config.semantic_merge_fact_threshold
                ),
                unresolved_issue_similarity_threshold=(
                    self.config.semantic_merge_issue_threshold
                ),
            ),
        )

    # 作用：把当前最优节点、搜索进度和规则原子写入检查点，便于异常后恢复或交给外部验证器。
    def _write_checkpoint(
        self,
        *,
        task: TaskSpec,
        graph: SearchGraph,
        transitions: list[TransitionRecord],
        total_tool_calls: int,
        stop_reason: str,
    ) -> None:
        if self.checkpoint_path is None:
            return
        best = self._best_node(graph)
        verified_success = (
            stop_reason == "verified_success"
            or (
                stop_reason == "running"
                and any(item.assessment.verified_success for item in transitions)
            )
        )
        payload = {
            "task_id": task.task_id,
            "search_algorithm": self.search_algorithm,
            "succeeded": verified_success,
            "verified_success": verified_success,
            "model_task_success_claimed": any(
                item.assessment.task_success for item in transitions
            ),
            "model_task_success_claim_count": sum(
                1 for item in transitions if item.assessment.task_success
            ),
            "candidate_success_count": sum(
                1 for item in transitions if item.assessment.candidate_success
            ),
            "stop_reason": stop_reason,
            "total_tool_calls": total_tool_calls,
            "transitions_completed": len(transitions),
            "interaction_rounds": len(transitions),
            "scheduling_trace": self._scheduling_trace,
            "initial_iteration_budget": self.config.max_iterations,
            "initial_tool_call_budget": self.config.max_total_tool_calls,
            "reserved_final_verification_tool_calls": (
                self._verification_reserve_tool_calls
            ),
            "final_verification_tool_calls": self._final_verification_tool_calls,
            "hard_iteration_budget": math.ceil(
                self.config.max_iterations * self.config.budget_multiplier
            ),
            "hard_tool_call_budget": math.ceil(
                self.config.max_total_tool_calls * self.config.budget_multiplier
            ),
            "base_children_per_node": self.config.base_children_per_node,
            "max_children_per_node": self.config.max_children_per_node,
            "frontier_max_entries_per_direction": (
                self.config.frontier_max_entries_per_direction
            ),
            "frontier_stale_after_iterations": (
                self.config.frontier_stale_after_iterations
            ),
            "frontier_stale_min_attempts": self.config.frontier_stale_min_attempts,
            "model_failures": self._model_failure_count,
            "semantic_coverage_rate": self._core_coverage_rate(best.context),
            "core_semantic_coverage_rate": self._core_coverage_rate(best.context),
            "discovered_semantic_coverage_rate": semantic_coverage_rate(best.context),
            "core_semantic_direction_ids": sorted(self._core_direction_ids()),
            "success_judge_mode": self.config.success_judge_mode,
            "success_judge_usage": self._success_judge_usage(),
            "success_judge_decisions": self._success_judge_decisions,
            "experience_funnel_events": dict(self._experience_events),
            "best_context": best.context.to_dict(),
            "best_workspace": best.snapshot.location,
            "task_rules": [asdict(rule) for rule in self.rule_store.all()],
        }
        path = self.checkpoint_path
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=list),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as error:
            logger.warning("[检查点] 写入失败：%s", _safe_model_error(error))

    # 作用：根据一次真实状态转移提炼recommend或avoid规则，并为失败规则确定合适的作用范围。
    def _distill_rule(self, task: TaskSpec, transition: TransitionRecord) -> None:
        status = transition.assessment.direction_status
        if status == "exploring":
            return
        read_only_coverage = status == "covered" and not transition.outcome.workspace_changed
        kind = "avoid" if status == "failed" or read_only_coverage else "recommend"
        failure_kind: FailureKind = "none"
        scope: RuleScope = "semantic_strategy"
        action_signature = ""
        command_signatures: tuple[str, ...] = ()
        sharing_scope: Literal["task", "environment"] = "task"
        applicable_environment_fingerprints: tuple[str, ...] = ()
        if read_only_coverage:
            failure_kind = "duplicate_action"
            scope = "exact_action"
            action_signature = transition.action.signature()
            guidance = (
                "This read-only action already produced sufficient evidence. Reuse the fact and advance the solution instead of repeating the same action."
            )
        elif status == "failed":
            failure_kind, scope, command_signatures, guidance = (
                _failed_rule_metadata(transition)
            )
            if scope == "exact_action":
                action_signature = transition.action.signature()
            #工具缺失和底层命令语法错误与某个候选补丁无关，可在任务内跨分支共享。
            #路径、环境、策略和语义冲突可能随文件状态变化，只共享给相同环境指纹。
            if not (
                scope == "exact_command"
                and failure_kind in {"tool_missing", "command_syntax"}
            ):
                sharing_scope = "environment"
                applicable_environment_fingerprints = tuple(
                    dict.fromkeys(
                        (
                            transition.outcome.parent_snapshot.fingerprint,
                            transition.outcome.resulting_snapshot.fingerprint,
                        )
                    )
                )
        else:
            guidance = (
                transition.action.expected_effect
                or transition.action.rationale
                or transition.assessment.feedback
            )
            #成功修改经验只适用于产生它的代码状态。相同文件树的兄弟分支可复用，
            #不同候选补丁仍保持隔离。
            if transition.outcome.workspace_changed:
                sharing_scope = "environment"
                applicable_environment_fingerprints = (
                    transition.outcome.parent_snapshot.fingerprint,
                )
        rule_ids_before = {rule.rule_id for rule in self.rule_store.all()}
        shared_rule = self.rule_store.add(
            task_id=task.task_id,
            kind=kind,
            semantic_direction_id=transition.action.semantic_direction_id,
            action_name=transition.action.name,
            evidence=transition.assessment.feedback,
            semantic_direction_label=transition.action.semantic_direction_label,
            condition=_rule_condition_from_context(transition.state_before),
            guidance=guidance,
            failure_kind=failure_kind,
            scope=scope,
            action_signature=action_signature,
            command_signatures=command_signatures,
            sharing_scope=sharing_scope,
            applicable_environment_fingerprints=(
                applicable_environment_fingerprints
            ),
        )
        if shared_rule.rule_id not in rule_ids_before:
            self._count_experience(f"{shared_rule.kind}_rules_created")
        logger.info(
            "[经验共享] 已整理%s规则%s：共享范围=%s，失败类型=%s",
            shared_rule.kind,
            shared_rule.rule_id,
            shared_rule.sharing_scope,
            shared_rule.failure_kind,
        )

        #通过真实功能验证的命令本身是一种可迁移经验：它不携带候选补丁内容，
        #但能告诉其他分支应怎样验收，因此作为任务级recommend规则单独保存。
        if transition.outcome.functional_validation_succeeded:
            verifier_signatures = tuple(
                command.normalized()
                for command in transition.action.verification_commands
            )
            if verifier_signatures:
                rule_ids_before = {rule.rule_id for rule in self.rule_store.all()}
                verifier_rule = self.rule_store.add(
                    task_id=task.task_id,
                    kind="recommend",
                    semantic_direction_id=(
                        transition.action.semantic_direction_id
                    ),
                    action_name="reuse_functional_verifier",
                    evidence=(
                        "Independent functional verification passed: "
                        + " | ".join(verifier_signatures)
                    ),
                    semantic_direction_label=(
                        transition.action.semantic_direction_label
                    ),
                    condition=(
                        "Use when validating a candidate solution in this task."
                    ),
                    guidance=(
                        "Reuse a previously successful read-only functional verifier: "
                        + " | ".join(verifier_signatures)
                    ),
                    command_signatures=verifier_signatures,
                    sharing_scope="task",
                )
                if verifier_rule.rule_id not in rule_ids_before:
                    self._count_experience("recommend_rules_created")
                logger.info(
                    "[经验共享] 已共享成功功能验证配方%s，供其他分支复用",
                    verifier_rule.rule_id,
                )

    # 作用：登记通过独立功能验证的候选节点，并维护当前证据最强的保底候选解。
    def _register_verified_candidate(
        self,
        graph: SearchGraph,
        node: SearchNode,
        commands: tuple[CommandSpec, ...],
    ) -> None:
        """保存通过独立功能验证的候选；该资格不参与在线优先级。"""

        self._candidate_verification_commands[node.node_id] = commands
        if node.node_id not in self._verified_candidate_node_ids:
            self._verified_candidate_node_ids.append(node.node_id)
        current = (
            graph.nodes.get(self._incumbent_candidate_node_id)
            if self._incumbent_candidate_node_id is not None
            else None
        )
        if current is None or _verified_candidate_key(
            node,
            len(commands),
        ) > _verified_candidate_key(
            current,
            len(self._candidate_verification_commands.get(current.node_id, ())),
        ):
            self._incumbent_candidate_node_id = node.node_id
            logger.info(
                "[候选解] 已保存通过%d条功能验证的提交候选：%s",
                len(commands),
                node.node_id,
            )

    # 作用：提交前依次复验已保存候选，选择验证通过的最优节点，并在失败时安全回退。
    def _finalize_best_node(self, graph: SearchGraph) -> SearchNode:
        """提交前重放候选验证；失败时按证据强度回退到更早候选。"""

        ordered_ids: list[str] = []
        for node_id in (
            self._incumbent_verified_success_node_id,
            self._incumbent_candidate_node_id,
        ):
            if node_id is not None and node_id not in ordered_ids:
                ordered_ids.append(node_id)
        remaining = sorted(
            (
                graph.nodes[node_id]
                for node_id in self._verified_candidate_node_ids
                if node_id in graph.nodes and node_id not in ordered_ids
            ),
            key=lambda node: _verified_candidate_key(
                node,
                len(self._candidate_verification_commands.get(node.node_id, ())),
            ),
            reverse=True,
        )
        ordered_ids.extend(node.node_id for node in remaining)

        verify = getattr(self.environment, "verify", None)
        if ordered_ids and not callable(verify):
            #轻量测试环境没有复验接口时，保留首次真实功能验证的候选。
            selected = graph.nodes[ordered_ids[0]]
            self._finalized_node_id = selected.node_id
            return selected

        for node_id in ordered_ids:
            node = graph.nodes[node_id]
            commands = self._candidate_verification_commands.get(node_id, ())
            remaining_verification_calls = max(
                0,
                self._final_verification_budget
                - self._final_verification_tool_calls,
            )
            if len(commands) > remaining_verification_calls:
                logger.warning(
                    "[最终验证] 候选%s需要%d次调用，但复验额度仅剩%d次；"
                    "跳过该候选以保持总预算",
                    node_id,
                    len(commands),
                    remaining_verification_calls,
                )
                continue
            try:
                results: tuple[CommandResult, ...] = verify(node.snapshot, commands)
            except (OSError, RuntimeError, ValueError) as error:
                logger.warning(
                    "[最终验证] 候选%s复验异常，尝试更早候选：%s",
                    node_id,
                    error,
                )
                continue
            self._final_verification_tool_calls += len(results)
            if results and all(result.succeeded for result in results):
                logger.info("[最终验证] 候选%s复验通过，锁定最终提交", node_id)
                self._finalized_node_id = node_id
                return node
            logger.warning("[最终验证] 候选%s复验失败，尝试更早候选", node_id)

        if ordered_ids:
            # 最终复验失败只能撤销“已验证成功”，不能抹掉已经形成的非空候选。
            # 外部 benchmark 仍应获得当前证据最强的补丁并独立评分；否则一次偶发的
            # 复验失败会把可用修复退化成空提交，混淆“内部确信度”和“实际解题率”。
            selected = graph.nodes[ordered_ids[0]]
            selected.terminal = False
            self._finalized_node_id = selected.node_id
            logger.warning(
                "[候选解] 所有已保存候选均未通过末次复验；保留最佳非空候选%s供外部评测，"
                "但内部状态保持失败",
                selected.node_id,
            )
            return selected

        if not ordered_ids and self._fallback_candidate_node_id in graph.nodes:
            selected = graph.nodes[self._fallback_candidate_node_id]
            self._finalized_node_id = selected.node_id
            logger.warning(
                "[候选解] 没有通过功能验证的候选；仅回退到明确标记的未验证候选，"
                "不会提交探索性临时文件"
            )
            return selected

        self._finalized_node_id = graph.root().node_id
        logger.warning(
            "[候选解] 没有可复验的提交候选，返回初始工作区而不是探索性临时文件"
        )
        return graph.root()

    # 作用：按照最终锁定节点、成功节点、已验证候选和回退候选的优先级取得当前最佳节点。
    def _best_node(self, graph: SearchGraph) -> SearchNode:
        if self._finalized_node_id in graph.nodes:
            return graph.nodes[self._finalized_node_id]
        terminal_nodes = [node for node in graph.nodes.values() if node.terminal]
        if terminal_nodes:
            if self._incumbent_verified_success_node_id in graph.nodes:
                return graph.nodes[self._incumbent_verified_success_node_id]
            return max(terminal_nodes, key=_successful_node_key)
        if self._incumbent_candidate_node_id in graph.nodes:
            return graph.nodes[self._incumbent_candidate_node_id]
        if self._fallback_candidate_node_id in graph.nodes:
            return graph.nodes[self._fallback_candidate_node_id]
        return max(
            graph.nodes.values(),
            key=lambda node: semantic_coverage_rate(node.context),
        )


# 作用：生成成功节点的排序键，按语义覆盖率选择证据最完整的节点。
def _successful_node_key(node: SearchNode) -> tuple[float]:
    return (semantic_coverage_rate(node.context),)


# 作用：生成已验证候选的排序键，优先比较验证数量，再比较覆盖率。
def _verified_candidate_key(
    node: SearchNode,
    verification_count: int,
) -> tuple[int, float]:
    return (
        verification_count,
        semantic_coverage_rate(node.context),
    )


# 作用：从执行前上下文提取精简的规则适用条件，避免保存冗长事实日志和完整命令输出。
def _rule_condition_from_context(context: StructuredContext) -> str:
    parts = [
        *(f"unresolved: {item}" for item in context.unresolved_issues[:3]),
        *(f"plan: {item}" for item in context.incomplete_plans[:3]),
    ]
    if context.environment_summary:
        parts.append(f"environment: {context.environment_summary}")
    return " | ".join(parts)[:1200]


# 作用：分析失败转移的具体原因，返回失败类型、规则作用域、命令签名和后续指导。
def _failed_rule_metadata(
    transition: TransitionRecord,
) -> tuple[FailureKind, RuleScope, tuple[str, ...], str]:
    failed_validation = tuple(
        result
        for result in transition.outcome.validation_results
        if not result.succeeded
    )
    if failed_validation:
        return (
            "command_syntax",
            "exact_action",
            (),
            "The automatic syntax or conflict-marker check failed after the edit. Preserve the error evidence, but do not reuse this exact editing action.",
        )
    failed_commands = tuple(
        result
        for result in (
            transition.outcome.command_results
            + transition.outcome.functional_validation_results
        )
        if not result.succeeded
    )
    if not failed_commands:
        feedback = transition.assessment.feedback.casefold()
        conflict_markers = (
            "contradict", "conflict", "inconsistent", "invalid assumption",
            "矛盾", "冲突", "不一致", "错误假设",
        )
        if any(marker in feedback for marker in conflict_markers):
            return (
                "semantic_conflict",
                "semantic_strategy",
                (),
                "This strategy conflicts with verified facts. Avoid only actions that rely on the same premise.",
            )
        return (
            "strategy_failure",
            "semantic_strategy",
            (),
            transition.action.expected_effect
            or transition.action.rationale
            or transition.assessment.feedback,
        )

    diagnostic = "\n".join(
        f"{result.stderr}\n{result.stdout}" for result in failed_commands
    ).casefold()
    return_codes = {result.return_code for result in failed_commands}
    if any(result.timed_out or result.blocked for result in failed_commands):
        failure_kind: FailureKind = "environment_error"
        guidance = "The command hit a timeout or an execution-environment restriction. Avoid only the original command; repair the environment or reduce the command's scope first."
    elif (
        127 in return_codes
        or "command not found" in diagnostic
        or "not recognized as an internal or external command" in diagnostic
        or "不是内部或外部命令" in diagnostic
    ):
        failure_kind = "tool_missing"
        guidance = "The tool required by the original command is unavailable. Avoid only that command form and use a tool that actually exists in the environment."
    elif any(
        marker in diagnostic
        for marker in (
            "no such file or directory", "filenotfounderror", "winerror 2",
            "cannot find the path", "cannot find the file", "系统找不到指定的文件",
            "找不到路径",
        )
    ):
        failure_kind = "path_error"
        guidance = "The path referenced by the original command does not exist. Avoid only the original command, verify the relative path, and then retry."
    elif any(
        marker in diagnostic
        for marker in (
            "syntaxerror", "syntax error", "unexpected token", "parse error",
            "unterminated", "invalid syntax", "unexpected eof", "语法错误",
        )
    ):
        failure_kind = "command_syntax"
        guidance = "The original command has a syntax or quoting error. Avoid only the identical command; after correcting its arguments, the same semantic direction remains valid."
    else:
        failure_kind = "environment_error"
        guidance = "The original CLI call failed. Avoid only the identical command; do not reject other implementation actions in the same semantic direction."
    return (
        failure_kind,
        "exact_command",
        tuple(result.command.normalized() for result in failed_commands),
        guidance,
    )


# 作用：从执行结果中提取第一条关键失败信息，生成供后续搜索使用的精简反馈。
def _failed_transition_feedback(outcome: ExecutionOutcome) -> str:
    failed = next(
        (
            result
            for result in (
                outcome.command_results
                + outcome.validation_results
                + outcome.functional_validation_results
            )
            if not result.succeeded
        ),
        None,
    )
    if failed is None:
        return "CLI execution produced no successful command result."
    if failed.blocked:
        reason = "command was blocked"
    elif failed.timed_out:
        reason = "command timed out"
    else:
        reason = f"return code {failed.return_code}"
    detail = (failed.stderr.strip() or failed.stdout.strip())[-1200:]
    command = " ".join(failed.command.argv)
    feedback = f"CLI command failed ({reason}): {command}"
    return f"{feedback}; output: {detail}" if detail else feedback


# 作用：在模型评估失败时保留CLI执行观测，说明该转移需要由后续节点重新判断。
def _model_failure_transition_feedback(outcome: ExecutionOutcome) -> str:
    observation = outcome.observation_text().strip()[-1200:]
    message = "Model evaluation was unavailable after successful CLI execution."
    return f"{message} Observation tail: {observation}" if observation else message


# 作用：把模型异常压缩成单行短文本，防止换行和过长内容污染运行日志。
def _safe_model_error(error: Exception) -> str:
    return str(error).replace("\r", " ").replace("\n", " ")[:240]
