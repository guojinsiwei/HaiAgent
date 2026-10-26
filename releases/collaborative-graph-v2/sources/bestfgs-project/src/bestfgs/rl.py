from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .models import TransitionRecord


#一条GRPO训练样本：记录状态、动作、语义方向、奖励拆分和组内相对优势
@dataclass(frozen=True, slots=True)
class GRPOSample:
    group_id: str
    iteration: int
    state_fingerprint: str
    action_id: str
    semantic_direction_id: str
    reward: float
    semantic_coverage_delta_reward: float
    task_success_reward: float
    advantage: float = 0.0


#以父搜索节点为group收集完整结构化轨迹
@dataclass(slots=True)
class GRPOBuffer:
    samples: list[GRPOSample] = field(default_factory=list)

    def add_transition(self, transition: TransitionRecord) -> None:
        self.samples.append(
            GRPOSample(
                group_id=transition.parent_node_id,
                iteration=transition.iteration,
                state_fingerprint=transition.state_before.fingerprint(),
                action_id=transition.action.action_id,
                semantic_direction_id=transition.action.semantic_direction_id,
                reward=transition.reward.total,
                semantic_coverage_delta_reward=transition.reward.semantic_coverage_delta,
                task_success_reward=transition.reward.task_success_reward,
            )
        )

    #组内标准化：(动作奖励-组平均奖励)/组内标准差
    def with_group_relative_advantages(self) -> tuple[GRPOSample, ...]:
        grouped: dict[str, list[GRPOSample]] = {}
        for sample in self.samples:
            grouped.setdefault(sample.group_id, []).append(sample)

        normalized: list[GRPOSample] = []
        for group in grouped.values():
            mean_reward = sum(item.reward for item in group) / len(group)
            variance = sum((item.reward - mean_reward) ** 2 for item in group) / len(group)
            scale = variance**0.5
            for item in group:
                advantage = (item.reward - mean_reward) / scale if scale > 1e-12 else 0.0
                normalized.append(
                    GRPOSample(
                        group_id=item.group_id,
                        iteration=item.iteration,
                        state_fingerprint=item.state_fingerprint,
                        action_id=item.action_id,
                        semantic_direction_id=item.semantic_direction_id,
                        reward=item.reward,
                        semantic_coverage_delta_reward=item.semantic_coverage_delta_reward,
                        task_success_reward=item.task_success_reward,
                        advantage=advantage,
                    )
                )
        return tuple(sorted(normalized, key=lambda item: item.iteration))

    def to_dicts(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.with_group_relative_advantages()]


#训练阶段可使用的GRPO/PPO裁剪代理目标
def clipped_surrogate(
    *,
    probability_ratio: float,
    advantage: float,
    clip_epsilon: float = 0.2,
) -> float:
    clipped = min(max(probability_ratio, 1.0 - clip_epsilon), 1.0 + clip_epsilon)
    return min(probability_ratio * advantage, clipped * advantage)

