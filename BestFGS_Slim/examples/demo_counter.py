from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace

from cli_retrac_mcts.agent import TaskRunner
from cli_retrac_mcts.environment import CLIEnvironment
from cli_retrac_mcts.search_core import SearchConfig, SearchResult
from cli_retrac_mcts.models import (
    CommandResult,
    CommandSpec,
    EnvironmentSnapshot,
    ExecutionOutcome,
    MacroAction,
    StructuredContext,
    TaskSpec,
    TransitionAssessment,
    TransitionUpdate,
    new_id,
)


#最小测试环境：环境状态只有一个整数，每个宏动作对整数做加法
@dataclass(slots=True)
class CounterEnvironment(CLIEnvironment):
    initial_value: int = 0

    def initial_snapshot(self) -> EnvironmentSnapshot:
        return self._snapshot(self.initial_value)

    def restore(self, snapshot: EnvironmentSnapshot) -> EnvironmentSnapshot:
        return snapshot

    #模拟真实CLI执行，命令最后一个参数就是需要增加的数值
    def execute(
        self,
        snapshot: EnvironmentSnapshot,
        action: MacroAction,
        max_commands: int,
    ) -> ExecutionOutcome:
        value = int(snapshot.metadata["value"])
        results: list[CommandResult] = []
        for command in action.commands[:max_commands]:
            value += int(command.argv[-1])
            results.append(CommandResult(command, 0, str(value), "", 0.0))
        resulting = self._snapshot(value)
        remaining = max(0, max_commands - len(results))
        functional_results = self.verify(
            resulting,
            action.verification_commands[:remaining],
        )
        return ExecutionOutcome(
            snapshot,
            resulting,
            action,
            tuple(results),
            functional_validation_results=functional_results,
        )

    def verify(
        self,
        snapshot: EnvironmentSnapshot,
        commands: tuple[CommandSpec, ...],
    ) -> tuple[CommandResult, ...]:
        value = int(snapshot.metadata["value"])
        results: list[CommandResult] = []
        for command in commands:
            expected = int(command.argv[-1])
            succeeded = value == expected
            results.append(
                CommandResult(
                    command,
                    0 if succeeded else 1,
                    f"value={value}, expected={expected}",
                    "" if succeeded else "counter target mismatch",
                    0.0,
                )
            )
        return tuple(results)

    @staticmethod
    def _snapshot(value: int) -> EnvironmentSnapshot:
        return EnvironmentSnapshot(
            snapshot_id=new_id("counter"),
            location=f"counter://{value}",
            fingerprint=f"counter-{value}",
            summary=f"counter value is {value}",
            metadata={"value": value},
        )

#最小策略：目标是让计数器到达3，用它演示策略接口如何接入图搜索
@dataclass(slots=True)
class CounterPolicy:
    target: int = 3

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        value = self._value(kwargs["context"])
        return (self._action(self.target - value),) if value != self.target else ()

    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return tuple(self._action(delta) for delta in (2, 6, 1))[: kwargs["limit"]]

    #一次返回转移判断和压缩上下文，与真实模型适配器保持相同接口
    def update_transition(self, **kwargs) -> TransitionUpdate:
        before = self._value(kwargs["previous"])
        after = int(kwargs["outcome"].resulting_snapshot.metadata["value"])
        if after == self.target:
            assessment = TransitionAssessment(
                "covered",
                True,
                "The target value was reached.",
                kwargs["task"].required_success_criteria,
            )
        elif abs(self.target - after) < abs(self.target - before):
            assessment = TransitionAssessment(
                "exploring",
                False,
                "The action moved closer to the target.",
            )
        else:
            assessment = TransitionAssessment(
                "failed",
                False,
                "The action did not advance this direction.",
            )
        context = replace(
            kwargs["previous"],
            current_solution=f"counter={after}",
            environment_summary=f"value={after}",
        )
        return TransitionUpdate(assessment, context)

    def _action(self, delta: int) -> MacroAction:
        return MacroAction.create(
            name=f"add_{delta}",
            rationale="Explore the semantic direction of reaching the target value.",
            semantic_direction_id="reach_target",
            semantic_direction_label="Reach the target counter state",
            commands=(
                CommandSpec(
                    argv=("counter", "add", str(delta)),
                    description=f"add {delta} to the counter",
                ),
            ),
            verification_commands=(
                CommandSpec(
                    argv=("counter", "verify", str(self.target)),
                    description=f"verify that the counter equals {self.target}",
                ),
            ),
            intent="candidate",
            expected_effect="Move the counter toward the target.",
        )

    @staticmethod
    def _value(context: StructuredContext) -> int:
        if context.environment_summary.startswith("value="):
            return int(context.environment_summary.split("=", 1)[1])
        return 0

#组装任务、配置、环境和策略，运行一次完整的语义覆盖率引导搜索
def run_demo() -> SearchResult:
    task = TaskSpec.create(
        "Reach counter value 3.",
        success_criteria=("The counter equals 3.",),
    )
    config = SearchConfig(max_iterations=10, max_total_tool_calls=20)
    return TaskRunner(CounterEnvironment(), CounterPolicy(), config).run(task)

#演示程序入口：打印是否成功、停止原因和任务结束后的指标
def main() -> int:
    result = run_demo()
    print(
        json.dumps(
            {
                "succeeded": result.succeeded,
                "stop_reason": result.stop_reason,
                "post_hoc_indicators": asdict(result.post_hoc_indicators),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
