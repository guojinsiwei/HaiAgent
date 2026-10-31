from __future__ import annotations

from dataclasses import dataclass, replace
import heapq
import logging
import math

from .best_first_runtime import BestFirstSearchRuntime, _failed_rule_metadata
from .models import MacroAction, SearchGraph, SearchNode, TaskSpec, TransitionRecord
from .priority import (
    NodePriorityEvidence,
    PriorityBreakdown,
    calculate_priority,
    clamp01,
    compute_solve_pressure,
    phase_weights,
)
from .semantic import (
    semantic_coverage_rate,
    snapshot_changed_paths_from_root,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _FrontierEntry:
    kind: str
    node_id: str
    action_id: str
    direction_id: str
    priority: PriorityBreakdown
    inserted_at: int


class SemanticBestFirstGraphSearch(BestFirstSearchRuntime):
    """Phase-adaptive semantic best-first graph search.

    The BestFGS-owned runtime supplies environment transitions, snapshot
    isolation, task-local RE-TRAC memory, budgets and final verification.
    This class supplies the algorithm-specific global, evidence-ranked
    frontier and evidence-driven phase changes.
    """

    search_algorithm = "phase_adaptive_semantic_best_first"
    _best_first_active = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._reset_best_first_state()

    def _reset_best_first_state(self) -> None:
        self._solve_pressure = 0.0
        self._node_priority_evidence: dict[str, NodePriorityEvidence] = {}
        self._direction_failures: dict[str, int] = {}
        self._action_execution_counts: dict[str, int] = {}
        self._action_first_seen: dict[tuple[str, str], int] = {}
        self._node_direction_ids: dict[str, str] = {}
        self._direction_attempts: dict[str, int] = {}
        self._direction_last_evidence_iteration: dict[str, int] = {}
        self._last_direction_id = ""
        self._consecutive_direction_count = 0
        self._selected_frontier_node_id: str | None = None
        self._selected_frontier_action_id: str | None = None
        self._selected_priority: PriorityBreakdown | None = None
        self._frontier_size = 0
        self._frontier_raw_size = 0
        self._frontier_pruned_dominated = 0
        self._frontier_pruned_stale = 0
        self._frontier_pruned_direction_quota = 0
        self._frontier_reactivated = 0
        self._frontier_iteration = 0
        self._frontier_score_gap: float | None = None
        self._frontier_uncertainty_bonus = 0
        self._frontier_stagnation_bonus = 0
        self._empty_frontier_recoveries = 0
        self._recovery_batches: dict[str, int] = {}
        self._retired_action_ids: dict[str, set[str]] = {}
        self._environment_failures: dict[str, dict[str, str]] = {}

    def search(self, *, task, initial_context):
        self._reset_best_first_state()
        logger.info(
            "[BestFGS] 使用阶段自适应语义最佳优先图搜索"
        )
        return super().search(task=task, initial_context=initial_context)

    def _capacity_action_ids(self, node: SearchNode) -> set[str]:
        return super()._capacity_action_ids(node) - self._retired_action_ids.get(node.node_id, set())

    def _can_expand_node(self, node: SearchNode) -> bool:
        signatures = self._capacity_action_ids(node)
        capacity = self._active_child_limit(node)
        if len(signatures) >= capacity:
            return False
        # One bootstrap plus enough three-action batches to reach the active
        # 3..6 capacity.  This is semantic capacity, not progressive widening.
        batch_width = max(1, self.config.expansion_width)
        batch_limit = max(
            self.config.max_expansion_batches_per_node,
            capacity,  # A model can return one action even when asked for three.
            1 + math.ceil(max(0, capacity - 1) / batch_width),
        )
        return node.expansion_batches < max(batch_limit, self._recovery_batches.get(node.node_id, 0))

    def _recover_empty_frontier(self, graph: SearchGraph, iteration: int) -> bool:
        status = self._planning_budget_status()
        if (self._empty_frontier_recoveries >= 2 or self._budget_planning_blocked
                or int(status["maximum_commands_for_next_action"]) < 1):
            return False
        candidates = []
        for node in graph.nodes.values():
            if node.terminal or self._path_from_root(graph, node.node_id) is None:
                continue
            failures = self._environment_failures.get(node.node_id, {})
            retired = self._retired_action_ids.get(node.node_id, set())
            recoverable = [key for key in failures if key not in retired]
            if len(self._capacity_action_ids(node)) >= self._active_child_limit(node) and not recoverable:
                continue
            priority = self._priority_for_expansion(node, graph, iteration)
            candidates.append((priority.band, priority.score, node, recoverable))
        if not candidates:
            return False
        _, _, node, recoverable = max(candidates, key=lambda item: item[:2])
        detail = "Propose a distinct targeted action from the unresolved task requirements."
        if recoverable:
            signature = recoverable[-1]
            # Keep the edge and duplicate history, release only its active capacity.
            self._retired_action_ids.setdefault(node.node_id, set()).add(signature)
            detail = self._environment_failures[node.node_id][signature]
        self._empty_frontier_recoveries += 1
        self._recovery_batches[node.node_id] = node.expansion_batches + 1
        node.exhausted = False
        issue = (
            "Runtime frontier recovery: " + detail
            + " Recheck dependencies and paths. A missing-tool probe is an expected observation; "
            "handle its exit status so it does not abort the repair. Use an explicit bounded "
            "timeout for installation. Do not repeat failed commands unchanged."
        )
        graph.update_context(node, replace(
            node.context,
            unresolved_issues=tuple(dict.fromkeys((*node.context.unresolved_issues, issue))),
            incomplete_plans=tuple(dict.fromkeys((*node.context.incomplete_plans, issue))),
        ))
        logger.info("[BestFGS] 空前沿恢复 %d/2：保留失败历史，恢复一个动作规划机会",
                    self._empty_frontier_recoveries)
        return True

    def _maybe_activate_solve_mode(
        self,
        graph: SearchGraph,
        iteration: int,
        *,
        task: TaskSpec | None = None,
    ) -> None:
        status = self._planning_budget_status()
        active_tool_budget = int(status["active_tool_call_budget"])
        reserve = int(status["reserved_final_verification_tool_calls"])
        candidate_maturity = max(
            (item.candidate_maturity for item in self._node_priority_evidence.values()),
            default=0.0,
        )
        self._solve_pressure = compute_solve_pressure(
            previous=self._solve_pressure,
            semantic_coverage=(
                self._knowledge_board.core_semantic_coverage_rate()
                if self._knowledge_board is not None
                else 0.0
            ),
            coverage_threshold=self.config.semantic_coverage_switch_threshold,
            iteration=iteration,
            max_iterations=int(status["active_iteration_budget"]),
            used_tool_calls=int(status["used_tool_calls"]),
            action_tool_budget=max(1, active_tool_budget - reserve),
            candidate_maturity=candidate_maturity,
        )
        candidate_ready = bool(
            candidate_maturity >= 0.50
            or self._incumbent_candidate_node_id
            or self._fallback_candidate_node_id
        )
        if (
            self._solve_mode
            or self._knowledge_board is None
            or (iteration <= 1 and not candidate_ready)
            or (
                self._solve_pressure < self.config.solve_mode_pressure_threshold
                and not candidate_ready
            )
        ):
            return

        promoted = self._knowledge_board.audit_completeness(
            task_goal=task.goal if task is not None else graph.root().context.task_goal,
            success_criteria=task.success_criteria if task is not None else (),
            contexts=tuple(node.context for node in graph.nodes.values()),
        )
        if promoted:
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
        self._solve_mode = True
        # Pending exploration actions stay in the frontier.  Their novelty
        # weight falls automatically, so useful alternatives remain recoverable.
        logger.info(
            "[BestFGS] 进入求解模式：pressure=%.2f candidate_ready=%s；"
            "保留有效前沿，改用进展/recommend/候选精修主导的优先级",
            self._solve_pressure,
            candidate_ready,
        )

    def _has_mature_candidate_evidence(self) -> bool:
        return any(
            item.candidate_maturity >= 0.60
            for item in self._node_priority_evidence.values()
        )

    def _adaptive_width_bonus(self, node: SearchNode) -> int:
        """按前沿不确定性/停滞扩宽，不读取节点访问次数。"""

        open_ids = {
            item.direction_id
            for item in node.context.semantic_directions
            if item.status != "covered"
        }
        uncertain = bool(
            self._frontier_score_gap is not None
            and self._frontier_score_gap <= 0.08
        )
        stagnating = any(
            self._direction_failures.get(direction_id, 0) >= 2
            for direction_id in open_ids
        )
        self._frontier_uncertainty_bonus = int(uncertain)
        self._frontier_stagnation_bonus = int(stagnating)
        return int(uncertain) + int(stagnating)

    def _select(
        self,
        graph: SearchGraph,
        task: TaskSpec,
        *,
        iteration: int,
    ):
        self._frontier_iteration = iteration
        self._selected_frontier_node_id = None
        self._selected_frontier_action_id = None
        self._selected_priority = None

        # Expansion is lazy: a state is asked for candidates only when it has
        # no pending action and its state priority wins globally.
        expansion_attempts = 0
        maximum_expansion_attempts = max(1, len(graph.nodes) * (self.config.max_children_per_node + 2) + 2)
        while expansion_attempts <= maximum_expansion_attempts:
            heap: list[tuple[int, float, float, int, _FrontierEntry]] = []
            sequence = 0
            maximum_commands = int(
                self._planning_budget_status()["maximum_commands_for_next_action"]
            )
            for node in tuple(graph.nodes.values()):
                if node.terminal:
                    continue
                self._sync_node_knowledge(graph, node)
                self._refresh_pending_actions(node)
                for action in node.pending_actions:
                    required_calls = min(
                        len(action.commands) + len(action.verification_commands),
                        self.config.max_commands_per_macro_action,
                    )
                    if required_calls > maximum_commands:
                        continue
                    breakdown = self._priority_for_action(node, action, iteration)
                    first_seen = self._action_first_seen[
                        (node.state_key(), action.signature())
                    ]
                    entry = _FrontierEntry(
                        "action",
                        node.node_id,
                        action.action_id,
                        action.semantic_direction_id
                        or self._node_direction_ids.get(node.node_id, ""),
                        breakdown,
                        first_seen,
                    )
                    heapq.heappush(
                        heap,
                        (
                            -breakdown.band,
                            -breakdown.score,
                            -breakdown.aging_bonus,
                            sequence,
                            entry,
                        ),
                    )
                    sequence += 1

                if not node.pending_actions and self._can_expand_node(node):
                    breakdown = self._priority_for_expansion(node, graph, iteration)
                    entry = _FrontierEntry(
                        "expand",
                        node.node_id,
                        "",
                        self._node_direction_ids.get(node.node_id, ""),
                        breakdown,
                        iteration,
                    )
                    heapq.heappush(
                        heap,
                        (
                            -breakdown.band,
                            -breakdown.score,
                            -breakdown.aging_bonus,
                            sequence,
                            entry,
                        ),
                    )
                    sequence += 1

            self._frontier_raw_size = len(heap)
            if not heap:
                self._frontier_size = 0
                if self._recover_empty_frontier(graph, iteration):
                    continue
                return None, []

            ranked = [heapq.heappop(heap)[-1] for _ in range(len(heap))]
            active = self._prune_frontier_entries(ranked, iteration=iteration)
            # 求解阶段落实“有Recommend就先利用”。这不是提示词偏好，而是
            # 全局前沿上的确定性门控；只有全图没有可执行Recommend才回到
            # 普通候选、Avoid规避候选或新方向扩展。
            recommended = [
                item for item in active
                if item.kind == "action" and item.priority.recommend > 0
            ]
            if self._solve_mode and recommended:
                active = recommended
                self._count_experience_once(
                    "recommend_frontier_priority_wins",
                    str(iteration),
                    recommended[0].node_id,
                    recommended[0].action_id,
                )
            self._frontier_size = len(active)
            if not active:
                return None, []
            if len(active) >= 2 and active[0].priority.band == active[1].priority.band:
                self._frontier_score_gap = abs(
                    active[0].priority.score - active[1].priority.score
                )
            else:
                self._frontier_score_gap = None
            entry = active[0]
            node = graph.nodes.get(entry.node_id)
            if node is None or node.terminal:
                continue
            if entry.kind == "expand":
                previous_batches = node.expansion_batches
                self._populate_actions(graph, node, task, initial=False)
                expansion_attempts += 1
                if node.expansion_batches == previous_batches:
                    node.exhausted = True
                continue

            path = self._path_from_root(graph, node.node_id)
            if path is None:
                # A stale graph entry cannot be restored safely.
                node.pending_actions[:] = [
                    action
                    for action in node.pending_actions
                    if action.action_id != entry.action_id
                ]
                continue
            self._selected_frontier_node_id = node.node_id
            self._selected_frontier_action_id = entry.action_id
            self._selected_priority = entry.priority
            logger.info(
                "[BestFGS] 选择全局前沿动作：band=%d score=%.3f "
                "pressure=%.2f frontier=%d/%d",
                entry.priority.band,
                entry.priority.score,
                entry.priority.solve_pressure,
                self._frontier_size,
                self._frontier_raw_size,
            )
            return node, path

        logger.warning("[BestFGS] 候选生成连续无结果，停止空转")
        return None, []

    @staticmethod
    def _dominates(left: _FrontierEntry, right: _FrontierEntry) -> bool:
        """Whether ``left`` is no worse on every useful signal than ``right``."""

        a = left.priority
        b = right.priority
        no_worse = (
            a.band >= b.band
            and a.score >= b.score
            and a.progress >= b.progress
            and a.recommend >= b.recommend
            and a.novelty >= b.novelty
            and a.information_gain >= b.information_gain
            and a.candidate_maturity >= b.candidate_maturity
            and a.cost_penalty <= b.cost_penalty
            and a.repeat_penalty <= b.repeat_penalty
            and a.failure_penalty <= b.failure_penalty
        )
        strictly_better = (
            a.band > b.band
            or a.score > b.score
            or a.progress > b.progress
            or a.recommend > b.recommend
            or a.novelty > b.novelty
            or a.information_gain > b.information_gain
            or a.candidate_maturity > b.candidate_maturity
            or a.cost_penalty < b.cost_penalty
            or a.repeat_penalty < b.repeat_penalty
            or a.failure_penalty < b.failure_penalty
        )
        return no_worse and strictly_better

    def _stale_direction_ids(self, iteration: int) -> set[str]:
        return {
            direction_id
            for direction_id, attempts in self._direction_attempts.items()
            if direction_id
            and attempts >= self.config.frontier_stale_min_attempts
            and iteration
            - self._direction_last_evidence_iteration.get(direction_id, iteration)
            >= self.config.frontier_stale_after_iterations
        }

    def _prune_frontier_entries(
        self,
        ranked: list[_FrontierEntry],
        *,
        iteration: int,
    ) -> list[_FrontierEntry]:
        """Soft-prune the ranked frontier without deleting graph state.

        Entries are already in best-first order.  A suppressed entry is
        reconsidered on every later selection, and the best suppressed entry
        is reactivated when pruning would otherwise empty the frontier.
        """

        self._frontier_pruned_dominated = 0
        self._frontier_pruned_stale = 0
        self._frontier_pruned_direction_quota = 0
        self._frontier_reactivated = 0
        if not ranked:
            return []

        stale_directions = self._stale_direction_ids(iteration)
        fresh: list[_FrontierEntry] = []
        for entry in ranked:
            if entry.direction_id and entry.direction_id in stale_directions:
                self._frontier_pruned_stale += 1
                continue
            fresh.append(entry)

        non_dominated: list[_FrontierEntry] = []
        for entry in fresh:
            if entry.direction_id and any(
                kept.direction_id == entry.direction_id
                and self._dominates(kept, entry)
                for kept in non_dominated
            ):
                self._frontier_pruned_dominated += 1
                continue
            non_dominated.append(entry)

        active: list[_FrontierEntry] = []
        direction_counts: dict[str, int] = {}
        for entry in non_dominated:
            direction_id = entry.direction_id
            if (
                direction_id
                and direction_counts.get(direction_id, 0)
                >= self.config.frontier_max_entries_per_direction
            ):
                self._frontier_pruned_direction_quota += 1
                continue
            active.append(entry)
            if direction_id:
                direction_counts[direction_id] = (
                    direction_counts.get(direction_id, 0) + 1
                )

        if not active:
            active.append(ranked[0])
            self._frontier_reactivated = 1

        pruned = (
            self._frontier_pruned_dominated
            + self._frontier_pruned_stale
            + self._frontier_pruned_direction_quota
        )
        if pruned:
            logger.info(
                "[BestFGS] 前沿软剪枝：原始=%d 活跃=%d "
                "支配=%d 停滞=%d 方向配额=%d 恢复=%d",
                len(ranked),
                len(active),
                self._frontier_pruned_dominated,
                self._frontier_pruned_stale,
                self._frontier_pruned_direction_quota,
                self._frontier_reactivated,
            )
        return active

    def _populate_actions(
        self,
        graph: SearchGraph,
        node: SearchNode,
        task: TaskSpec,
        *,
        initial: bool,
    ) -> None:
        super()._populate_actions(graph, node, task, initial=initial)
        # Preserve direction diversity without a Beam layer: exploration keeps
        # one pending action per direction, solving may keep two alternatives.
        per_direction_limit = 2 if self._solve_mode else 1
        counts: dict[str, int] = {}
        diverse: list[MacroAction] = []
        for action in node.pending_actions:
            direction_id = action.semantic_direction_id
            if counts.get(direction_id, 0) >= per_direction_limit:
                continue
            counts[direction_id] = counts.get(direction_id, 0) + 1
            diverse.append(action)
        node.pending_actions[:] = diverse

    def _take_pending_action(
        self,
        node: SearchNode,
        *,
        max_tool_calls: int | None = None,
    ) -> MacroAction | None:
        self._refresh_pending_actions(node)
        if node.node_id == self._selected_frontier_node_id:
            for index, action in enumerate(node.pending_actions):
                required = min(
                    len(action.commands) + len(action.verification_commands),
                    self.config.max_commands_per_macro_action,
                )
                if (
                    action.action_id == self._selected_frontier_action_id
                    and (max_tool_calls is None or required <= max_tool_calls)
                ):
                    selected = node.pending_actions.pop(index)
                    self._record_action_selection(selected)
                    return selected
        selected = super()._take_pending_action(
            node,
            max_tool_calls=max_tool_calls,
        )
        if selected is not None:
            self._record_action_selection(selected)
        return selected

    def _record_action_selection(self, action: MacroAction) -> None:
        signature = action.signature()
        self._action_execution_counts[signature] = (
            self._action_execution_counts.get(signature, 0) + 1
        )
        if action.semantic_direction_id == self._last_direction_id:
            self._consecutive_direction_count += 1
        else:
            self._last_direction_id = action.semantic_direction_id
            self._consecutive_direction_count = 1

    def _priority_for_action(
        self,
        node: SearchNode,
        action: MacroAction,
        iteration: int,
    ) -> PriorityBreakdown:
        key = (node.state_key(), action.signature())
        first_seen = self._action_first_seen.setdefault(key, iteration)
        direction_streak = (
            self._consecutive_direction_count
            if action.semantic_direction_id == self._last_direction_id
            else 0
        )
        return calculate_priority(
            context=node.context,
            action=action,
            evidence=self._node_priority_evidence.get(
                node.node_id,
                NodePriorityEvidence(),
            ),
            solve_pressure=self._solve_pressure,
            direction_failures=self._direction_failures.get(
                action.semantic_direction_id,
                0,
            ),
            action_repeat_count=self._action_execution_counts.get(
                action.signature(),
                0,
            ),
            consecutive_direction_count=direction_streak,
            estimated_tool_calls=(
                len(action.commands) + len(action.verification_commands)
            ),
            max_commands_per_action=self.config.max_commands_per_macro_action,
            waiting_rounds=max(0, iteration - first_seen),
        )

    def _priority_for_expansion(
        self,
        node: SearchNode,
        graph: SearchGraph,
        iteration: int,
    ) -> PriorityBreakdown:
        evidence = self._node_priority_evidence.get(
            node.node_id,
            NodePriorityEvidence(),
        )
        weights = phase_weights(self._solve_pressure)
        directions = tuple(node.context.semantic_directions)
        open_directions = sum(item.status != "covered" for item in directions)
        novelty = (
            open_directions / len(directions)
            if directions
            else (1.0 if node.context.unresolved_issues else 0.0)
        )
        info_gain = clamp01(len(node.context.unresolved_issues) / 3)
        progress = clamp01(evidence.real_progress)
        maturity = clamp01(evidence.candidate_maturity)
        path = self._path_from_root(graph, node.node_id) or []
        cost_penalty = 0.05 * clamp01(len(path) / max(1, self.config.max_iterations))
        score = (
            weights.progress * progress
            + weights.novelty * novelty
            + weights.information_gain * info_gain
            + weights.candidate_maturity * maturity
            - cost_penalty
        )
        verification_gaps = tuple(
            item for item in node.context.unresolved_issues
            if item.strip().casefold().startswith("independent verification gap:")
        )
        if verification_gaps and maturity >= 0.50:
            # 先让模型在当前候选快照上产生针对 Judge 缺口的修复/复验动作；
            # 该状态无可生成动作后，旧的广域前沿才会重新成为首选。
            band = 4
            score += 0.30
        elif progress >= 0.75 or maturity >= 0.75:
            band = 3
        elif progress >= 0.40:
            band = 2
        elif novelty > 0 or info_gain > 0:
            band = 1
        else:
            band = 0
        return PriorityBreakdown(
            band=band,
            score=round(score, 6),
            solve_pressure=round(self._solve_pressure, 6),
            progress=round(progress, 6),
            recommend=0.0,
            avoid_compliance=0.0,
            novelty=round(novelty, 6),
            information_gain=round(info_gain, 6),
            candidate_maturity=round(maturity, 6),
            cost_penalty=round(cost_penalty, 6),
            repeat_penalty=0.0,
            failure_penalty=0.0,
            aging_bonus=0.0,
        )

    def _distill_rule(self, task: TaskSpec, transition: TransitionRecord) -> None:
        super()._distill_rule(task, transition)
        self._record_transition_evidence(transition)

    def _record_transition_evidence(self, transition: TransitionRecord) -> None:
        outcome = transition.outcome
        assessment = transition.assessment
        if (not outcome.commands_succeeded and not outcome.workspace_changed
                and not any(result.blocked for result in outcome.command_results)):
            kind, _, _, guidance = _failed_rule_metadata(transition)
            if kind in {"environment_error", "tool_missing", "path_error"}:
                self._environment_failures.setdefault(transition.parent_node_id, {})[
                    transition.action.signature()
                ] = guidance
        progress = 0.0
        if outcome.commands_succeeded:
            progress = max(progress, 0.10)
        if assessment.direction_status == "covered":
            progress = max(progress, 0.30)
        if outcome.workspace_changed and outcome.validation_succeeded:
            progress = max(progress, 0.45)
        criteria_total = max(1, len(transition.state_before.unresolved_issues))
        if assessment.satisfied_success_criteria:
            progress = max(
                progress,
                min(0.70, 0.70 * len(assessment.satisfied_success_criteria) / criteria_total),
            )
        if outcome.functional_validation_succeeded:
            # 一次窄功能测试只说明候选可用，不能等同于任务完成。
            # 满进展只授予通过运行时硬门槛和独立风险审计的节点。
            progress = max(progress, 0.80)
        if assessment.verified_success:
            progress = 1.0

        maturity = 0.0
        if outcome.workspace_changed:
            maturity += 0.25
        if outcome.validation_succeeded:
            maturity += 0.25
        if outcome.functional_validation_attempted:
            maturity += 0.25
        if outcome.functional_validation_succeeded:
            maturity += 0.25
        if outcome.functional_validation_succeeded and not assessment.verified_success:
            maturity = min(maturity, 0.75)
        self._node_priority_evidence[transition.child_node_id] = NodePriorityEvidence(
            real_progress=clamp01(progress),
            candidate_maturity=clamp01(maturity),
            last_direction_status=assessment.direction_status,
        )

        failed = (
            assessment.direction_status == "failed"
            or not outcome.commands_succeeded
            or not outcome.validation_succeeded
            or (
                outcome.functional_validation_attempted
                and not outcome.functional_validation_succeeded
            )
            or assessment.judge_verdict in {"fail", "insufficient_evidence"}
        )
        direction_id = transition.action.semantic_direction_id
        if direction_id:
            self._node_direction_ids[transition.child_node_id] = direction_id
            self._direction_attempts[direction_id] = (
                self._direction_attempts.get(direction_id, 0) + 1
            )
            self._direction_last_evidence_iteration.setdefault(
                direction_id,
                transition.iteration,
            )
            before_facts = {
                (item.claim, item.verified, item.semantic_direction_id)
                for item in transition.state_before.facts_and_evidence
            }
            after_facts = {
                (item.claim, item.verified, item.semantic_direction_id)
                for item in transition.state_after.facts_and_evidence
            }
            material_evidence = (
                transition.semantic_coverage_after
                > transition.semantic_coverage_before + 1e-9
                or outcome.workspace_changed
                or outcome.functional_validation_succeeded
                or bool(assessment.satisfied_success_criteria)
                or assessment.direction_status == "covered"
                or after_facts != before_facts
                or transition.state_after.unresolved_issues
                != transition.state_before.unresolved_issues
            )
            if material_evidence:
                self._direction_last_evidence_iteration[direction_id] = (
                    transition.iteration
                )
        if failed:
            self._direction_failures[direction_id] = (
                self._direction_failures.get(direction_id, 0) + 1
            )
        elif progress >= 0.40:
            self._direction_failures[direction_id] = 0

    def _decision_trace_fields(
        self,
        node: SearchNode,
        action: MacroAction,
    ) -> dict[str, object]:
        return {
            "search_algorithm": self.search_algorithm,
            "frontier_size": self._frontier_size,
            "frontier_raw_size": self._frontier_raw_size,
            "empty_frontier_recoveries": self._empty_frontier_recoveries,
            "frontier_pruning": {
                "dominated": self._frontier_pruned_dominated,
                "stale": self._frontier_pruned_stale,
                "direction_quota": self._frontier_pruned_direction_quota,
                "reactivated": self._frontier_reactivated,
            },
            "solve_pressure": round(self._solve_pressure, 6),
            "frontier_score_gap": (
                round(self._frontier_score_gap, 6)
                if self._frontier_score_gap is not None else None
            ),
            "adaptive_width": {
                "uncertainty_bonus": self._frontier_uncertainty_bonus,
                "stagnation_bonus": self._frontier_stagnation_bonus,
            },
            "priority": (
                self._selected_priority.as_dict()
                if self._selected_priority is not None
                else {}
            ),
        }
