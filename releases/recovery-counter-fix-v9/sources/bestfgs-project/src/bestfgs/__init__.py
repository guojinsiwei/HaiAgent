"""Continuous CLI execution with optional advice; legacy graph APIs stay explicit."""

__version__ = "0.18.1"

# 包的对外接口：使用者可以直接从 bestfgs 导入这些核心类。
from .agent import TaskRunner as LegacyTaskRunner
from .best_first import SemanticBestFirstGraphSearch
from .best_first_runtime import (
    BestFGSConfig,
    BestFirstSearchRuntime,
    RewardConfig,
    SearchResult,
)
from .models import (
    InitialSemanticPlan,
    MacroAction,
    SemanticDirection,
    StructuredContext,
    TaskSpec,
)
from .retrac_adapter import ModelProvider, RetracModelConfig, RetracPolicyAdapter
from .collaboration import CollaborativePolicyAdapter
from .lean_runtime import LeanTaskRunner
from .lean_protocol import LeanConfig
TaskRunner = LeanTaskRunner

__all__ = [
    "LeanTaskRunner",
    "LeanConfig",
    "LegacyTaskRunner",
    "CollaborativePolicyAdapter",
    "BestFGSConfig",
    "BestFirstSearchRuntime",
    "InitialSemanticPlan",
    "MacroAction",
    "ModelProvider",
    "RewardConfig",
    "RetracModelConfig",
    "RetracPolicyAdapter",
    "SearchResult",
    "SemanticDirection",
    "SemanticBestFirstGraphSearch",
    "StructuredContext",
    "TaskRunner",
    "TaskSpec",
]
