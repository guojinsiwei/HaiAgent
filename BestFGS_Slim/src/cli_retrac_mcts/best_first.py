from __future__ import annotations

from dataclasses import dataclass
import heapq
import logging
import math

from .search_core import GraphSearchCore
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
    priority: PriorityBreakdown
    inserted_at: int


class SemanticBestFirstGraphSearch(GraphSearchCore):
    """Phase-adaptive semantic best-first graph search.

    The parent class supplies the already tested environment transition,
    snapshot isolation, RE-TRAC memory, task-local rules, budget handling and
    final verification lifecycle.  This class replaces UCB tree descent and
    reward backpropagation with a global, evidence-ranked frontier.
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
        self._last_direction_id = ""
        self._consecutive_direction_count = 0
        self._selected_frontier_node_id: str | None = None
        self._selected_frontier_action_id: str | None = None
        self._selected_priority: PriorityBreakdown | None = None
        self._frontier_size = 0
        self._frontier_iteration = 0

    def search(self, *, task, initial_context):
        self._reset_best_first_state()
        logger.info(
            "[BestFGS] 使用阶段自适应语义最佳优先图搜索；"
            "UCB、rollout和奖励回传不参与在线选择"
        )
        return super().search(task=task, initial_context=initial_context)

    def _can_expand_node(self, node: SearchNode) -> bool:
        signatures = set(node.tried_action_ids)
        signatures.update(action.signature() for action in node.pending_actions)
        capacity = self._active_child_limit(node)
        if len(signatures) >= capacity:
            return False
        # One bootstrap plus enough three-action batches to reach the active
        # 3..6 capacity.  This is semantic capacity, not progressive widening.
        batch_width = max(1, self.config.expansion_width)
        batch_limit = max(
            self.config.max_expansion_batches_per_node,
            1 + math.ceil(max(0, capacity - 1) / batch_width),
        )
        return node.expansion_batches < batch_limit

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
        self._solve_pressure = compute_solve_pressure(
            previous=self._solve_pressure,
            semantic_coverage=(
                self._knowledge_board.semantic_coverage_rate()
                if self._knowledge_board is not None
                else 0.0
            ),
            coverage_threshold=self.config.semantic_coverage_switch_threshold,
            iteration=iteration,
            max_iterations=int(status["active_iteration_budget"]),
            used_tool_calls=int(status["used_tool_calls"]),
            action_tool_budget=max(1, active_tool_budget - reserve),
        )
        if self._solve_mode or self._solve_pressure < 1.0 or self._knowledge_board is None:
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
            "[BestFGS] 求解压力达到1.0：保留全部有效前沿，"
            "改用进展/recommend/候选成熟度主导的优先级"
        )

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
        maximum_expansion_attempts = max(1, len(graph.nodes) * 3)
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
                        "action", node.node_id, action.action_id, breakdown, first_seen
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
                        "expand", node.node_id, "", breakdown, iteration
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

            self._frontier_size = len(heap)
            if not heap:
                return None, []

            entry = heapq.heappop(heap)[-1]
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
                "pressure=%.2f frontier=%d",
                entry.priority.band,
                entry.priority.score,
                entry.priority.solve_pressure,
                self._frontier_size,
            )
            return node, path

        logger.warning("[BestFGS] 候选生成连续无结果，停止空转")
        return None, []

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
        per_direction_limit = 2 if self._solve_pressure >= 1.0 else 1
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
        if progress >= 0.75 or maturity >= 0.75:
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
        )
        direction_id = transition.action.semantic_direction_id
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
            "solve_pressure": round(self._solve_pressure, 6),
            "priority": (
                self._selected_priority.as_dict()
                if self._selected_priority is not None
                else {}
            ),
        }
