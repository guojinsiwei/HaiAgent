from __future__ import annotations

from dataclasses import dataclass

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
}

COVERAGE_DIAGNOSTIC_TIMING: dict[str, str] = {
    "discovered_semantic_coverage_rate": "online_diagnostic",
}

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

#事后指标分析器，输入完整轨迹后一次性计算，搜索过程中不会调用这些结果指导Selection
class PostHocIndicatorAnalyzer:
    """Computes the three post-hoc indicators only after the episode ends."""

    #计算有效探索比例、知识复用率、工具调用冗余率
    @staticmethod
    def analyze(transitions: list[TransitionRecord]) -> PostHocIndicatorReport:
        if not transitions:
            return PostHocIndicatorReport(0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0)

        #有效探索：尝试过的方向中，最终得到covered结果的比例
        attempted = {item.action.semantic_direction_id for item in transitions}
        covered = {
            item.action.semantic_direction_id
            for item in transitions
            if direction_status(item.state_after, item.action.semantic_direction_id) == "covered"
        }
        effective_ratio = len(covered & attempted) / len(attempted) if attempted else 0.0

        #知识复用：全部已执行宏动作中，有多少动作在生成或选择时应用了推荐规则
        rule_guided = [item for item in transitions if item.action.applied_rule_ids]
        reuse_rate = len(rule_guided) / len(transitions)

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
            rule_guided_actions=len(rule_guided),
            redundant_tool_calls=redundant,
            total_tool_calls=total_calls,
            final_discovered_semantic_coverage_rate=(
                transitions[-1].discovered_semantic_coverage_after
            ),
        )
