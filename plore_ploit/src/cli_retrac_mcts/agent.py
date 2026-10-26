from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .environment import CLIEnvironment
from .mcts import CoverageGuidedMCTS, MCTSConfig, PolicyModel, RewardConfig, SearchResult
from .models import StructuredContext, TaskSpec
from .rules import TaskRuleStore
#此文件主要用于启动任务前的准备和启动任务

#最小任务入口：模型调用和工具执行复用RE-TRAC或由实验环境实现，不在这里重复封装
@dataclass(slots=True)
class TaskRunner:
    environment: CLIEnvironment
    policy: PolicyModel
    mcts_config: MCTSConfig = field(default_factory=MCTSConfig)
    reward_config: RewardConfig = field(default_factory=RewardConfig)
    checkpoint_path: Path | None = None
    #先构建初始retrac上下文，再初始化规则库和传入MCTS的运行参数
    def run(self, task: TaskSpec) -> SearchResult:
        initial_context = StructuredContext(
            task_goal=task.goal,
            unresolved_issues=task.success_criteria,
            incomplete_plans=("Identify and explore explicit semantic directions.",),
        )
        rules = TaskRuleStore(task_id=task.task_id)
        search = CoverageGuidedMCTS(
            environment=self.environment,
            policy=self.policy,
            rule_store=rules,
            mcts_config=self.mcts_config,
            reward_config=self.reward_config,
            checkpoint_path=self.checkpoint_path,
        )
        return search.search(task=task, initial_context=initial_context)
