"""Public, harness-independent contracts. No executor or model dependency."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal


@dataclass(frozen=True)
class TerminalEvent:
    task_id: str
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    cwd: str = ""
    # Host-supplied revisions, NOT inferred by hashing command output.
    workspace: str | None = None
    environment: str | None = None
    timed_out: bool = False
    blocked: bool = False
    output_truncated: bool = False
    input_digest: str = ""  # Identity of stdin, when supplied by the executor.
    file_revisions: dict[str, str | None] = field(default_factory=dict)
    workspace_before: str | None = None
    # Model-declared approach label. The component records it but does not infer
    # semantic equivalence between different labels.
    strategy: str = ""
    # Model-declared current objective. This is a rolling focus, not a host claim
    # that the objective has been completed or that a full plan is correct.
    subgoal: str = ""
    # Host-derived coarse action profile. It is deterministic evidence for
    # task-local loop control, not an LLM semantic-equivalence judgement.
    direction_key: str = ""
    direction_summary: str = ""
    direction_targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class Limits:
    recent_count: int = 6
    recent_bytes: int = 16_000
    memory_count: int = 12
    memory_bytes: int = 12_000
    state_count: int = 12
    state_bytes: int = 8_000
    strategy_count: int = 8
    subgoal_count: int = 6
    direction_count: int = 12
    direction_repeat_threshold: int = 3
    direction_diagnostic_threshold: int = 8
    feedback_chars: int = 2_400
    scan_chars: int = 64_000
    memory_ttl_steps: int = 80

    def __post_init__(self):
        for name, value in vars(self).items():
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.feedback_chars < 128 or self.scan_chars < self.feedback_chars:
            raise ValueError("require scan_chars >= feedback_chars >= 128")
        if min(self.recent_bytes, self.memory_bytes, self.state_bytes) < 2:
            raise ValueError("serialized collection budgets must accommodate [] or {}")


@dataclass(frozen=True)
class Evidence:
    id: str
    step: int
    command: str
    quote: str
    exit_code: int | None
    cwd: str
    workspace: str | None
    environment: str | None
    file_revisions: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryCandidate:
    """An optional host suggestion. Evidence IDs must exist in THIS component.

    Host-authored generalizations are hypotheses, not automatically proven causes.
    Leave dependencies at both revisions unless the host can justify narrower scope.
    """
    conclusion: str
    applies_when: str
    evidence_ids: tuple[str, ...]
    kind: Literal["constraint", "finding", "procedure", "failure", "recovery"] = "finding"
    dependencies: tuple[str, ...] = ("workspace", "environment")
    strength: Literal["observed", "hypothesis"] = "hypothesis"
    value: int = 2
    direction_key: str = ""
    targets: tuple[str, ...] = ()


class BudgetExceeded(ValueError):
    """The mandatory task/constraints/scope/latest-feedback payload does not fit."""


@dataclass(frozen=True)
class PromptView:
    content: str
    units: int
    unit_name: str
    selected_memory_ids: tuple[str, ...]
    omitted_memories: int
    omitted_recent: int


Counter = Callable[[str], int]
