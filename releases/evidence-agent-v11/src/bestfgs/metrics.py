from __future__ import annotations

from dataclasses import dataclass, field

from .models import TransitionRecord
from .semantic import direction_status

'''
专门在任务结束后计算实验指标。它输出最终语义覆盖率，并根据完整转移轨迹计算有效探索比例、知识复用率和工具调用冗余率；
后三项不会参与在线 Selection 或奖励，只用于事后分析，
'''

#四项指标的时间边界：只有语义覆盖率是事中指标，其余三个必须任务结束后计算
INDICATOR_TIMING: dict[str, str] = {
    "semantic_coverage_rate": "online",
    "effective_exploration_ratio": "post_hoc",
    "knowledge_reuse_rate": "post_hoc",
    "tool_call_redundancy_rate": "post_hoc",
    "experience_funnel": "post_hoc",
}

COVERAGE_DIAGNOSTIC_TIMING: dict[str, str] = {
    "discovered_semantic_coverage_rate": "online_diagnostic",
}

@dataclass(frozen=True, slots=True)
class ExperienceFunnelReport:
    """任务内 RE-TRAC 经验从产生到生效的完整漏斗。"""

    recommend_rules_created: int = 0
    avoid_rules_created: int = 0
    retrieval_events: int = 0
    recommend_rules_exposed: int = 0
    avoid_rules_exposed: int = 0
    semantic_avoid_exposures: int = 0
    model_rule_selected_actions: int = 0
    actions_evaluated_against_rules: int = 0
    recommend_actions_validated: int = 0
    recommend_actions_enqueued: int = 0
    recommend_actions_executed: int = 0
    recommend_actions_effective: int = 0
    recommend_frontier_priority_wins: int = 0
    avoid_actions_blocked: int = 0
    avoid_actions_validated: int = 0
    avoid_actions_enqueued: int = 0
    avoid_actions_executed: int = 0
    avoid_actions_effective: int = 0
    all_blocked_fallback_overrides: int = 0
    recommend_enqueue_rate: float = 0.0
    recommend_execution_rate: float = 0.0
    recommend_effectiveness_rate: float = 0.0
    avoid_block_rate: float = 0.0
    avoid_execution_rate: float = 0.0
    avoid_effectiveness_rate: float = 0.0


#任务结束后的指标报告，同时保留分子分母对应的原始计数，便于实验分析
@dataclass(frozen=True, slots=True)
class PostHocIndicatorReport:
    #固定核心方向覆盖率；运行中新发现方向不会改变其分母。
    final_semantic_coverage_rate: float
    effective_exploration_ratio: float
    knowledge_reuse_rate: float
    tool_call_redundancy_rate: float
    attempted_semantic_directions: int
    covered_semantic_directions: int
    rule_guided_actions: int
    redundant_tool_calls: int
    total_tool_calls: int
    #动态发现覆盖率用于解释地图扩张，不参与在线奖励。
    final_discovered_semantic_coverage_rate: float = 0.0
    experience_funnel: ExperienceFunnelReport = field(
        default_factory=ExperienceFunnelReport
    )

#事后指标分析器，输入完整轨迹后一次性计算，搜索过程中不会调用这些结果指导Selection
class PostHocIndicatorAnalyzer:
    """Computes the three post-hoc indicators only after the episode ends."""

    #计算有效探索比例、知识复用率、工具调用冗余率
    @staticmethod
    def analyze(
        transitions: list[TransitionRecord],
        *,
        experience_events: dict[str, int] | None = None,
    ) -> PostHocIndicatorReport:
        events = dict(experience_events or {})
        if not transitions:
            return PostHocIndicatorReport(
                0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0,
                experience_funnel=_experience_funnel(events, (), ()),
            )

        #有效探索：尝试过的方向中，最终得到covered结果的比例
        attempted = {item.action.semantic_direction_id for item in transitions}
        covered = {
            item.action.semantic_direction_id
            for item in transitions
            if direction_status(item.state_after, item.action.semantic_direction_id) == "covered"
        }
        effective_ratio = len(covered & attempted) / len(attempted) if attempted else 0.0

        #知识复用：全部已执行宏动作中，有多少动作在生成或选择时应用了推荐规则
        recommend_guided = [
            item for item in transitions if item.action.applied_rule_ids
        ]
        avoid_guided = [
            item for item in transitions if item.action.avoided_rule_ids
        ]
        experience_guided = [
            item for item in transitions
            if item.action.applied_rule_ids or item.action.avoided_rule_ids
        ]
        effective_recommend_guided = [
            item for item in recommend_guided if _rule_guided_action_was_effective(item)
        ]
        effective_avoid_guided = [
            item for item in avoid_guided if _rule_guided_action_was_effective(item)
        ]
        reuse_rate = len(experience_guided) / len(transitions)

        #工具冗余：同一语义方向中重复相同规范化命令，且没有带来首次覆盖
        seen_calls: set[tuple[str, str]] = set()
        redundant = 0
        total_calls = 0
        for transition in transitions:
            direction_id = transition.action.semantic_direction_id
            newly_covered = (
                direction_status(transition.state_before, direction_id) != "covered"
                and direction_status(transition.state_after, direction_id) == "covered"
            )
            for result in transition.outcome.command_results:
                total_calls += 1
                key = (direction_id, result.command.normalized())
                if key in seen_calls and not newly_covered:
                    redundant += 1
                seen_calls.add(key)

        redundancy_rate = redundant / total_calls if total_calls else 0.0
        return PostHocIndicatorReport(
            final_semantic_coverage_rate=transitions[-1].semantic_coverage_after,
            effective_exploration_ratio=effective_ratio,
            knowledge_reuse_rate=reuse_rate,
            tool_call_redundancy_rate=redundancy_rate,
            attempted_semantic_directions=len(attempted),
            covered_semantic_directions=len(covered & attempted),
            rule_guided_actions=len(experience_guided),
            redundant_tool_calls=redundant,
            total_tool_calls=total_calls,
            final_discovered_semantic_coverage_rate=(
                transitions[-1].discovered_semantic_coverage_after
            ),
            experience_funnel=_experience_funnel(
                events,
                recommend_guided,
                effective_recommend_guided,
                avoid_guided,
                effective_avoid_guided,
            ),
        )


def _rule_guided_action_was_effective(transition: TransitionRecord) -> bool:
    outcome = transition.outcome
    return bool(
        transition.semantic_coverage_after
        > transition.semantic_coverage_before + 1e-9
        or outcome.functional_validation_succeeded
        or (outcome.workspace_changed and outcome.validation_succeeded)
        or (
            direction_status(
                transition.state_before,
                transition.action.semantic_direction_id,
            )
            != "covered"
            and direction_status(
                transition.state_after,
                transition.action.semantic_direction_id,
            )
            == "covered"
        )
    )


def _experience_funnel(
    events: dict[str, int],
    executed: list[TransitionRecord] | tuple[()],
    effective: list[TransitionRecord] | tuple[()],
    avoid_executed: list[TransitionRecord] | tuple[()] = (),
    avoid_effective: list[TransitionRecord] | tuple[()] = (),
) -> ExperienceFunnelReport:
    validated = max(0, int(events.get("recommend_actions_validated", 0)))
    enqueued = max(0, int(events.get("recommend_actions_enqueued", 0)))
    executed_count = len(executed)
    effective_count = len(effective)
    avoid_executed_count = len(avoid_executed)
    avoid_effective_count = len(avoid_effective)
    evaluated = max(0, int(events.get("actions_evaluated_against_rules", 0)))
    blocked = max(0, int(events.get("avoid_actions_blocked", 0)))
    return ExperienceFunnelReport(
        recommend_rules_created=max(0, int(events.get("recommend_rules_created", 0))),
        avoid_rules_created=max(0, int(events.get("avoid_rules_created", 0))),
        retrieval_events=max(0, int(events.get("retrieval_events", 0))),
        recommend_rules_exposed=max(0, int(events.get("recommend_rules_exposed", 0))),
        avoid_rules_exposed=max(0, int(events.get("avoid_rules_exposed", 0))),
        semantic_avoid_exposures=max(0, int(events.get("semantic_avoid_exposures", 0))),
        model_rule_selected_actions=max(0, int(events.get("model_rule_selected_actions", 0))),
        actions_evaluated_against_rules=evaluated,
        recommend_actions_validated=validated,
        recommend_actions_enqueued=enqueued,
        recommend_actions_executed=executed_count,
        recommend_actions_effective=effective_count,
        recommend_frontier_priority_wins=max(
            0, int(events.get("recommend_frontier_priority_wins", 0))
        ),
        avoid_actions_blocked=blocked,
        avoid_actions_validated=max(
            0, int(events.get("avoid_actions_validated", 0))
        ),
        avoid_actions_enqueued=max(
            0, int(events.get("avoid_actions_enqueued", 0))
        ),
        avoid_actions_executed=avoid_executed_count,
        avoid_actions_effective=avoid_effective_count,
        all_blocked_fallback_overrides=max(
            0, int(events.get("all_blocked_fallback_overrides", 0))
        ),
        recommend_enqueue_rate=enqueued / validated if validated else 0.0,
        recommend_execution_rate=executed_count / enqueued if enqueued else 0.0,
        recommend_effectiveness_rate=(
            effective_count / executed_count if executed_count else 0.0
        ),
        avoid_block_rate=blocked / evaluated if evaluated else 0.0,
        avoid_execution_rate=(
            avoid_executed_count
            / max(0, int(events.get("avoid_actions_enqueued", 0)))
            if int(events.get("avoid_actions_enqueued", 0)) > 0 else 0.0
        ),
        avoid_effectiveness_rate=(
            avoid_effective_count / avoid_executed_count
            if avoid_executed_count else 0.0
        ),
    )
