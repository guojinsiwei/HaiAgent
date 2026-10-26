from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .best_first_runtime import BestFGSConfig, PolicyModel, RewardConfig, SearchResult
from .best_first import SemanticBestFirstGraphSearch
from .environment import CLIEnvironment
from .models import StructuredContext, TaskSpec
from .rules import TaskRuleStore
from .success_judge import SuccessJudge
#此文件主要用于启动任务前的准备和启动任务

#最小任务入口：模型调用和工具执行复用RE-TRAC或由实验环境实现，不在这里重复封装
@dataclass(slots=True, init=False)
class TaskRunner:
    environment: CLIEnvironment
    policy: PolicyModel
    config: BestFGSConfig = field(default_factory=BestFGSConfig)
    reward_config: RewardConfig = field(default_factory=RewardConfig)
    checkpoint_path: Path | None = None
    success_judge: SuccessJudge | None = None

    def __init__(
        self,
        environment: CLIEnvironment,
        policy: PolicyModel,
        config: BestFGSConfig | None = None,
        reward_config: RewardConfig | None = None,
        checkpoint_path: Path | None = None,
        success_judge: SuccessJudge | None = None,
    ) -> None:
        self.environment = environment
        self.policy = policy
        self.config = config or BestFGSConfig()
        self.reward_config = reward_config or RewardConfig()
        self.checkpoint_path = checkpoint_path
        self.success_judge = success_judge

    #先构建初始RE-TRAC上下文，再初始化任务内规则库和BestFGS运行参数
    def run(self, task: TaskSpec) -> SearchResult:
        initial_context = StructuredContext(
            task_goal=task.goal,
            unresolved_issues=task.success_criteria,
            incomplete_plans=("Identify and explore explicit semantic directions.",),
        )
        rules = TaskRuleStore(task_id=task.task_id)
        search = SemanticBestFirstGraphSearch(
            environment=self.environment,
            policy=self.policy,
            rule_store=rules,
            config=self.config,
            reward_config=self.reward_config,
            checkpoint_path=self.checkpoint_path,
            success_judge=self.success_judge,
        )
        return search.search(task=task, initial_context=initial_context)
