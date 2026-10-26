from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from .models import (
    DirectionStatus,
    EvidenceItem,
    ExecutionOutcome,
    MacroAction,
    SemanticDirection,
    StructuredContext,
    stable_id,
)

'''
负责把探索过程组织到语义空间中。它计算语义覆盖率，维护语义方向的 unexplored、exploring、covered 和 failed 状态，
合并已验证事实，并通过 TaskKnowledgeBoard 将同一任务内可安全共享的只读事实传给后续节点；
同时判断两个结构化上下文是否语义等价、是否存在事实冲突，并为模型生成长度受控的上下文投影。
'''
_VERIFICATION_RANK = {"no": 0, "partial": 1, "yes": 2}
_FACT_VALUE_PATTERN = re.compile(
    r"0x[0-9a-f]+|\bv?\d+(?:\.\d+)*\b|(?:[a-z]:)?[\\/][^\s,;]+",
    re.IGNORECASE,
)
_FACT_WORD_PATTERN = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
_PATH_TOKEN_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/])?[A-Za-z0-9_.@+-]+(?:[\\/][A-Za-z0-9_.@+-]+)*"
)
_WORKSPACE_WIDE_EXECUTABLES = {
    "cargo", "ctest", "dotnet", "go", "gradle", "gradlew", "make", "mvn",
    "ninja", "nox", "npm", "pnpm", "pytest", "tox", "yarn",
}
_LOW_INFORMATION_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "detected", "for",
    "from", "in", "is", "it", "of", "on", "or", "the", "to", "was",
    "were", "with", "version", "当前", "已经", "得到", "显示", "检测",
}


def _normalized_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"[^\w\u3400-\u9fff./\\:-]+", " ", normalized)
    return " ".join(normalized.split())


def _fact_key(item: EvidenceItem) -> str:
    """Exact fact key deliberately excludes the evidence source."""

    return _normalized_text(item.claim)


def _fact_values(text: str) -> tuple[str, ...]:
    return tuple(
        value.removeprefix("v")
        for value in _FACT_VALUE_PATTERN.findall(_normalized_text(text))
    )


def _fact_features(text: str) -> frozenset[str]:
    normalized = _normalized_text(text)
    features = {
        token
        for token in _FACT_WORD_PATTERN.findall(normalized)
        if len(token) > 1 and token not in _LOW_INFORMATION_WORDS
    }
    for sequence in re.findall(r"[\u3400-\u9fff]+", normalized):
        for size in (2, 3):
            features.update(
                sequence[index:index + size]
                for index in range(max(0, len(sequence) - size + 1))
            )
    return frozenset(features)


def _fact_is_negative(text: str) -> bool:
    normalized = _normalized_text(text)
    return bool(
        re.search(
            r"\b(?:no|not|never|missing|absent|failed|false)\b|"
            r"\b(?:cannot|without)\b|不存在|没有|尚未|未找到|失败|错误|"
            r"不得|不能|不允许",
            normalized,
        )
    )


def _facts_mergeable(left: EvidenceItem, right: EvidenceItem) -> bool:
    left_claim = _fact_key(left)
    right_claim = _fact_key(right)
    if left_claim == right_claim:
        return True
    #近似表述只能在同一明确语义方向内合并，避免跨区域误吞不同结论
    if (
        not left.semantic_direction_id
        or left.semantic_direction_id != right.semantic_direction_id
    ):
        return False
    left_values = _fact_values(left.claim)
    right_values = _fact_values(right.claim)
    #版本、地址、路径等关键值不一致时必须保留为不同事实
    if left_values != right_values:
        return False
    if _fact_is_negative(left.claim) != _fact_is_negative(right.claim):
        return False
    left_features = _fact_features(left.claim)
    right_features = _fact_features(right.claim)
    if not left_features or not right_features:
        return False
    overlap = len(left_features.intersection(right_features))
    union = len(left_features.union(right_features))
    jaccard = overlap / union if union else 0.0
    sequence = difflib.SequenceMatcher(None, left_claim, right_claim).ratio()
    if left_values:
        return overlap >= 1 and jaccard >= 0.4
    return jaccard >= 0.75 or sequence >= 0.82


def _unique_text(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item:
            continue
        key = _normalized_text(item)
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


def _merge_fact_items(earlier: EvidenceItem, newer: EvidenceItem) -> EvidenceItem:
    #验证等级相同时保留父路径表述，使上下文指纹不会因为同义改写反复抖动
    primary = (
        newer
        if _VERIFICATION_RANK[newer.verified] > _VERIFICATION_RANK[earlier.verified]
        else earlier
    )
    secondary = earlier if primary is newer else newer
    sources = _unique_text(
        (
            primary.source,
            *primary.supporting_sources,
            secondary.source,
            *secondary.supporting_sources,
        )
    )
    aliases = _unique_text(
        (
            *primary.aliases,
            secondary.claim if _fact_key(primary) != _fact_key(secondary) else "",
            *secondary.aliases,
        )
    )
    return replace(
        primary,
        source=sources[0] if sources else primary.source,
        supporting_sources=sources[1:],
        aliases=aliases,
        semantic_direction_id=(
            primary.semantic_direction_id or secondary.semantic_direction_id
        ),
        workspace_dependencies=_unique_text(
            (*primary.workspace_dependencies, *secondary.workspace_dependencies)
        ),
        observed_at_fingerprint=(
            primary.observed_at_fingerprint or secondary.observed_at_fingerprint
        ),
    )


def _merge_fact_sequence(items: Iterable[EvidenceItem]) -> tuple[EvidenceItem, ...]:
    merged: list[EvidenceItem] = []
    for item in items:
        for index, earlier in enumerate(merged):
            if _facts_mergeable(earlier, item):
                merged[index] = _merge_fact_items(earlier, item)
                break
        else:
            merged.append(item)
    return tuple(merged)


def _normalized_workspace_paths(items: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for item in items:
        value = str(item).strip().replace("\\", "/")
        if not value:
            continue
        if value == "*":
            return ("*",)
        value = value.removeprefix("./").strip("/")
        if value:
            normalized.add(value)
    return tuple(sorted(normalized))


def _dependency_is_affected(dependency: str, changed_paths: tuple[str, ...]) -> bool:
    if dependency == "*" or "*" in changed_paths:
        return bool(changed_paths)
    dependency = dependency.rstrip("/")
    for changed in changed_paths:
        changed = changed.rstrip("/")
        if changed == dependency or changed.startswith(dependency + "/"):
            return True
    return False


def _evidence_is_current(
    dependencies: tuple[str, ...],
    changed_paths: tuple[str, ...],
) -> bool:
    return not any(
        _dependency_is_affected(dependency, changed_paths)
        for dependency in dependencies
    )


def snapshot_changed_paths_from_root(
    snapshot: Any,
    root_fingerprint: str,
) -> tuple[str, ...]:
    """Read compact root-relative change metadata with a conservative fallback."""

    raw = snapshot.metadata.get("changed_paths_from_root")
    if isinstance(raw, (list, tuple)):
        return _normalized_workspace_paths(str(item) for item in raw)
    if snapshot.fingerprint != root_fingerprint:
        return ("*",)
    return ()


def _candidate_workspace_paths(
    texts: Iterable[str],
    outcome: ExecutionOutcome,
) -> tuple[str, ...]:
    roots = (
        Path(outcome.parent_snapshot.location).resolve(),
        Path(outcome.resulting_snapshot.location).resolve(),
    )
    found: set[str] = set()
    for text in texts:
        for token in _PATH_TOKEN_PATTERN.findall(str(text)):
            token = token.strip(".,;:()[]{}<>\"'")
            if not token or token in {".", ".."}:
                continue
            candidate = Path(token)
            for root in roots:
                try:
                    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
                    relative = resolved.relative_to(root)
                    if not resolved.exists():
                        continue
                    is_directory = resolved.is_dir()
                except (OSError, ValueError, RuntimeError):
                    # Command text is untrusted, not necessarily a filename
                    # (e.g. a long base64 payload). Unresolvable evidence must
                    # not terminate the task or be treated as a valid dependency.
                    continue
                value = relative.as_posix()
                if value == ".":
                    return ("*",)
                found.add(value + "/" if is_directory else value)
                break
    return _normalized_workspace_paths(found)


def _command_workspace_dependencies(outcome: ExecutionOutcome) -> tuple[str, ...]:
    dependencies: set[str] = set(outcome.changed_workspace_paths)
    results = (
        outcome.command_results
        + outcome.functional_validation_results
    )
    for result in results:
        command = result.command
        executable = Path(command.argv[0]).name.casefold() if command.argv else ""
        workspace_wide = executable in _WORKSPACE_WIDE_EXECUTABLES
        if executable.startswith("python") and any(
            part.casefold() in {"pytest", "unittest"} for part in command.argv
        ):
            workspace_wide = True
        paths = _candidate_workspace_paths(
            (*command.argv, command.cwd, command.description),
            outcome,
        )
        if workspace_wide or not paths:
            dependencies.add("*")
        else:
            dependencies.update(paths)
    return _normalized_workspace_paths(dependencies)


def _fact_workspace_dependencies(
    item: EvidenceItem,
    outcome: ExecutionOutcome,
    action_dependencies: tuple[str, ...],
) -> tuple[str, ...]:
    explicit = _candidate_workspace_paths(
        (item.source, *item.supporting_sources, item.claim),
        outcome,
    )
    if explicit:
        return _normalized_workspace_paths((*explicit, *outcome.changed_workspace_paths))
    return action_dependencies


def bind_transition_evidence(
    previous: StructuredContext,
    compressed: StructuredContext,
    outcome: ExecutionOutcome,
    *,
    semantic_direction_id: str,
) -> tuple[StructuredContext, tuple[str, ...]]:
    """Attach runtime-derived file provenance without another model request."""

    action_dependencies = _command_workspace_dependencies(outcome)
    previous_by_key = {_fact_key(item): item for item in previous.facts_and_evidence}
    facts: list[EvidenceItem] = []
    for item in compressed.facts_and_evidence:
        earlier = previous_by_key.get(_fact_key(item))
        if earlier is not None and earlier.observed_at_fingerprint:
            item = replace(
                item,
                workspace_dependencies=earlier.workspace_dependencies,
                observed_at_fingerprint=earlier.observed_at_fingerprint,
            )
        elif item.verified == "yes":
            item = replace(
                item,
                semantic_direction_id=item.semantic_direction_id or semantic_direction_id,
                workspace_dependencies=_fact_workspace_dependencies(
                    item,
                    outcome,
                    action_dependencies,
                ),
                observed_at_fingerprint=outcome.resulting_snapshot.fingerprint,
            )
        facts.append(item)
    return replace(compressed, facts_and_evidence=tuple(facts)), action_dependencies


def invalidate_context_for_workspace_changes(
    context: StructuredContext,
    changed_paths: Iterable[str],
) -> StructuredContext:
    """Drop stale facts and reopen only semantic directions whose proof was affected."""

    changed = _normalized_workspace_paths(changed_paths)
    if not changed:
        return context
    retained_facts: list[EvidenceItem] = []
    invalid_direction_ids: set[str] = set()
    for item in context.facts_and_evidence:
        if item.workspace_dependencies and not _evidence_is_current(
            item.workspace_dependencies,
            changed,
        ):
            if item.semantic_direction_id:
                invalid_direction_ids.add(item.semantic_direction_id)
            continue
        retained_facts.append(item)
    directions: list[SemanticDirection] = []
    for item in context.semantic_directions:
        invalid = item.direction_id in invalid_direction_ids or (
            item.status == "covered"
            and item.workspace_dependencies
            and not _evidence_is_current(item.workspace_dependencies, changed)
        )
        if invalid:
            affected = ", ".join(changed[:4])
            directions.append(
                replace(
                    item,
                    status="unexplored",
                    evidence=(f"Previous coverage invalidated by workspace changes: {affected}",),
                    workspace_dependencies=(),
                    observed_at_fingerprint="",
                )
            )
        else:
            directions.append(item)
    return replace(
        context,
        facts_and_evidence=tuple(retained_facts),
        semantic_directions=tuple(directions),
    )

'''
语义等价节点合并
两条不同的搜索路径，如果最后工作区状态和认知状态基本相同，是否可以合并成一个节点？
满足以下条件合并：
已验证事实至少有 90% 相似；
未解决问题至少有 80% 相似。
  '''
@dataclass(frozen=True, slots=True)
class SemanticNodeMergeConfig:
    """Conservative thresholds used only after the environment fingerprint matches."""

    verified_fact_similarity_threshold: float = 0.90
    unresolved_issue_similarity_threshold: float = 0.80

    def validate(self) -> None:
        for name in (
            "verified_fact_similarity_threshold",
            "unresolved_issue_similarity_threshold",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


def _collection_features(items: Iterable[str]) -> frozenset[str]:
    features: set[str] = set()
    for item in items:
        features.update(_fact_features(item))
        features.update(_fact_values(item))
    return frozenset(features)

#计算事实相似匹配律
def _feature_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_features = _collection_features(left)
    right_features = _collection_features(right)
    if not left_features and not right_features:
        return 1.0
    if not left_features or not right_features:
        return 0.0
    return len(left_features & right_features) / len(left_features | right_features)


def _semantic_relation_score(left: str, right: str) -> float:
    """比较方向说明与事实/问题是否在谈同一个语义主题。"""

    left_normalized = _normalized_text(left)
    right_normalized = _normalized_text(right)
    if left_normalized == right_normalized:
        return 1.0
    left_features = _fact_features(left_normalized)
    right_features = _fact_features(right_normalized)
    overlap = 0.0
    if left_features and right_features:
        overlap = len(left_features & right_features) / min(
            len(left_features),
            len(right_features),
        )
    sequence = difflib.SequenceMatcher(
        None,
        left_normalized,
        right_normalized,
    ).ratio()
    return max(overlap, sequence)


def _verified_fact_similarity(
    left: tuple[EvidenceItem, ...],
    right: tuple[EvidenceItem, ...],
) -> float:
    """Symmetric matching rate after the existing value/polarity-safe fact normalizer."""

    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    unmatched = set(range(len(right)))
    matches = 0
    for earlier in left:
        for index in tuple(unmatched):
            if _facts_mergeable(earlier, right[index]):
                unmatched.remove(index)
                matches += 1
                break
    return 2 * matches / (len(left) + len(right))

#先找明显冲突，如果有明显冲突就直接拒绝合并，如一边肯定一边否定、同一语义方向得出相反结论
def _verified_facts_contradict(
    left: tuple[EvidenceItem, ...],
    right: tuple[EvidenceItem, ...],
) -> bool:
    """Reject obvious conflicts in the same semantic topic before similarity merging."""

    for earlier in left:
        for newer in right:
            if (
                earlier.semantic_direction_id
                and newer.semantic_direction_id
                and earlier.semantic_direction_id != newer.semantic_direction_id
            ):
                continue
            earlier_features = _fact_features(earlier.claim)
            newer_features = _fact_features(newer.claim)
            if not earlier_features or not newer_features:
                continue
            topic_overlap = len(earlier_features & newer_features) / min(
                len(earlier_features), len(newer_features)
            )
            if topic_overlap < 0.5:
                continue
            earlier_values = _fact_values(earlier.claim)
            newer_values = _fact_values(newer.claim)
            if earlier_values and newer_values and earlier_values != newer_values:
                return True
            if _fact_is_negative(earlier.claim) != _fact_is_negative(newer.claim):
                return True
    return False

#两个上下文必须有完全相同的一组directionid、且不能一边covered、一边failed
def _directions_compatible(
    left: tuple[SemanticDirection, ...],
    right: tuple[SemanticDirection, ...],
) -> bool:
    left_by_id = {item.direction_id: item for item in left}
    right_by_id = {item.direction_id: item for item in right}
    if set(left_by_id) != set(right_by_id):
        return False
    for direction_id, earlier in left_by_id.items():
        newer = right_by_id[direction_id]
        if {earlier.status, newer.status} == {"covered", "failed"}:
            return False
    return True


def _merge_equivalent_directions(
    left: tuple[SemanticDirection, ...],
    right: tuple[SemanticDirection, ...],
) -> tuple[SemanticDirection, ...]:
    status_rank = {"unexplored": 0, "failed": 1, "exploring": 2, "covered": 3}
    right_by_id = {item.direction_id: item for item in right}
    merged: list[SemanticDirection] = []
    for earlier in left:
        newer = right_by_id[earlier.direction_id]
        primary = newer if status_rank[newer.status] > status_rank[earlier.status] else earlier
        merged.append(
            replace(
                primary,
                evidence=_unique_text((*earlier.evidence, *newer.evidence)),
            )
        )
    return tuple(merged)

'''
最终入口 
前置条件：两个节点的环境指纹必须相同
合并必须满足：目标相同->语义方向集合兼容->已验证fact没有冲突->前面两个相似度阈值
'''
def merge_semantically_equivalent_contexts(
    left: StructuredContext,
    right: StructuredContext,
    *,
    config: SemanticNodeMergeConfig | None = None,
) -> StructuredContext | None:
    """Return a lossless union only when two same-environment contexts are equivalent.

    The environment fingerprint is intentionally checked by ``SearchGraph`` before this
    function is called. This function then uses structured fields, not an LLM judgment.
    """

    config = config or SemanticNodeMergeConfig()
    config.validate()
    if _normalized_text(left.task_goal) != _normalized_text(right.task_goal):
        return None
    if not _directions_compatible(left.semantic_directions, right.semantic_directions):
        return None

    left_verified = tuple(item for item in left.facts_and_evidence if item.verified == "yes")
    right_verified = tuple(item for item in right.facts_and_evidence if item.verified == "yes")
    if _verified_facts_contradict(left_verified, right_verified):
        return None
    if _verified_fact_similarity(
        left_verified,
        right_verified,
    ) < config.verified_fact_similarity_threshold:
        return None
    if _feature_similarity(
        left.unresolved_issues,
        right.unresolved_issues,
    ) < config.unresolved_issue_similarity_threshold:
        return None

    current_solution = left.current_solution
    if _normalized_text(current_solution) in {"", "none"}:
        current_solution = right.current_solution
    return replace(
        left,
        current_solution=current_solution,
        facts_and_evidence=_merge_fact_sequence(
            (*left.facts_and_evidence, *right.facts_and_evidence)
        ),
        analysis_and_conclusions=_unique_text(
            (*left.analysis_and_conclusions, *right.analysis_and_conclusions)
        ),
        unresolved_issues=_unique_text(
            (*left.unresolved_issues, *right.unresolved_issues)
        ),
        incomplete_plans=_unique_text(
            (*left.incomplete_plans, *right.incomplete_plans)
        ),
        semantic_directions=_merge_equivalent_directions(
            left.semantic_directions,
            right.semantic_directions,
        ),
        environment_summary=max(
            (left.environment_summary, right.environment_summary),
            key=len,
        ),
    )

'''
跨分支的知识分享但是只能共享工作区中的只读事实
'''

@dataclass(frozen=True, slots=True)
class CandidateSemanticDirection:
    """暂未进入覆盖率分母、等待证据或重复提议确认的语义方向。"""

    direction_id: str
    label: str
    proposal_count: int = 1
    supporting_reasons: tuple[str, ...] = ()


#任务级只读知识板：跨兄弟分支共享原始工作区上的已验证事实与语义地图，不共享文件修改
@dataclass(slots=True)
class TaskKnowledgeBoard:
    root_fingerprint: str
    _facts: list[EvidenceItem] = field(default_factory=list)
    _directions: dict[str, SemanticDirection] = field(default_factory=dict)
    #核心方向在初始规划和任务成功标准审计后冻结，用作可比较的在线覆盖分母。
    #后续发现的方向仍进入_directions，但只影响动态发现覆盖率。
    _core_direction_ids: set[str] = field(default_factory=set)
    _candidate_directions: dict[str, CandidateSemanticDirection] = field(
        default_factory=dict
    )

    @classmethod
    def create(cls, root_fingerprint: str, context: StructuredContext) -> "TaskKnowledgeBoard":
        board = cls(root_fingerprint=root_fingerprint)
        board._facts = list(
            _merge_fact_sequence(
                item for item in context.facts_and_evidence if item.verified == "yes"
            )
        )
        board._directions = {
            item.direction_id: item for item in context.semantic_directions
        }
        board._core_direction_ids = set(board._directions)
        return board

    #模型提出的方向进入任务级语义地图；这里只登记方向，不把分支状态横向传播
    def register_actions(self, actions: tuple[MacroAction, ...]) -> None:
        for action in actions:
            self._directions.setdefault(
                action.semantic_direction_id,
                SemanticDirection(
                    direction_id=action.semantic_direction_id,
                    label=action.semantic_direction_label,
                    status="unexplored",
                ),
            )
            self._remove_equivalent_candidate(
                action.semantic_direction_id,
                action.semantic_direction_label,
            )

    def register_directions(
        self,
        directions: tuple[SemanticDirection, ...],
        *,
        core: bool = True,
    ) -> None:
        """登记初始语义地图；它只定义搜索空间，不创建搜索边或 CLI 动作。"""

        for direction in directions:
            self._directions.setdefault(
                direction.direction_id,
                replace(direction, status="unexplored", evidence=()),
            )
            self._remove_equivalent_candidate(direction.direction_id, direction.label)
            if core:
                self._core_direction_ids.add(direction.direction_id)

    def mark_core_directions(
        self,
        directions: Iterable[SemanticDirection],
    ) -> None:
        """把初始成功标准审计补入的方向纳入固定核心覆盖空间。"""

        self._core_direction_ids.update(item.direction_id for item in directions)

    def defer_actions(
        self,
        proposed: tuple[MacroAction, ...],
        accepted: tuple[MacroAction, ...],
        context: StructuredContext,
    ) -> tuple[SemanticDirection, ...]:
        """保留未接纳动作的方向，但暂不把它们加入正式覆盖空间。"""

        accepted_signatures = {action.signature() for action in accepted}
        seen_candidates: set[str] = set()
        for action in proposed:
            if action.signature() in accepted_signatures:
                continue
            if self._has_equivalent_official_direction(
                action.semantic_direction_id,
                action.semantic_direction_label,
            ):
                continue
            candidate_key = self._find_candidate_key(
                action.semantic_direction_id,
                action.semantic_direction_label,
            )
            if candidate_key is None:
                candidate_key = action.semantic_direction_id
                self._candidate_directions[candidate_key] = CandidateSemanticDirection(
                    direction_id=action.semantic_direction_id,
                    label=action.semantic_direction_label,
                )
            elif candidate_key not in seen_candidates:
                earlier = self._candidate_directions[candidate_key]
                self._candidate_directions[candidate_key] = replace(
                    earlier,
                    proposal_count=earlier.proposal_count + 1,
                )
            seen_candidates.add(candidate_key)
        return self.promote_supported_candidates((context,))

    def promote_supported_candidates(
        self,
        contexts: tuple[StructuredContext, ...],
    ) -> tuple[SemanticDirection, ...]:
        """把获得事实/未决问题支持或跨轮重复出现的候选升级为正式方向。"""

        promoted: list[SemanticDirection] = []
        for candidate_key, candidate in tuple(self._candidate_directions.items()):
            reasons = list(candidate.supporting_reasons)
            topic = f"{candidate.direction_id} {candidate.label}"
            for context in contexts:
                for issue in context.unresolved_issues:
                    if _semantic_relation_score(topic, issue) >= 0.45:
                        reasons.append(f"unresolved_issue: {issue}")
                for fact in context.facts_and_evidence:
                    if (
                        fact.verified == "yes"
                        and _semantic_relation_score(topic, fact.claim) >= 0.50
                    ):
                        reasons.append(f"verified_fact: {fact.claim}")
            unique_reasons = _unique_text(reasons)
            candidate = replace(candidate, supporting_reasons=unique_reasons)
            self._candidate_directions[candidate_key] = candidate
            if candidate.proposal_count < 2 and not unique_reasons:
                continue
            direction = SemanticDirection(candidate.direction_id, candidate.label)
            self._directions.setdefault(direction.direction_id, direction)
            promoted.append(direction)
            del self._candidate_directions[candidate_key]
        return tuple(promoted)

    def audit_completeness(
        self,
        *,
        task_goal: str,
        success_criteria: tuple[str, ...],
        contexts: tuple[StructuredContext, ...],
    ) -> tuple[SemanticDirection, ...]:
        """求解前确保成功标准和仍未解决的问题都有正式语义方向承载。"""

        promoted = list(self.promote_supported_candidates(contexts))
        requirements = success_criteria or (task_goal,)
        audit_items = _unique_text(
            (
                *requirements,
                *(
                    issue
                    for context in contexts
                    for issue in context.unresolved_issues
                ),
            )
        )
        for item in audit_items:
            if self._text_has_official_direction(item):
                continue
            candidate_key = self._best_candidate_key_for_text(item)
            if candidate_key is not None:
                candidate = self._candidate_directions.pop(candidate_key)
                direction = SemanticDirection(candidate.direction_id, candidate.label)
            else:
                direction = SemanticDirection(
                    stable_id("direction", {"completeness_audit": _normalized_text(item)}),
                    item[:160],
                )
            self._directions.setdefault(direction.direction_id, direction)
            promoted.append(direction)
        return tuple(promoted)

    def enrich_for_planning(self, context: StructuredContext) -> StructuredContext:
        """只把候选方向作为计划提示交给模型，不改变节点地图或覆盖率。"""

        hints = tuple(
            f"Deferred semantic direction candidate ({item.direction_id}): {item.label}"
            for item in self._candidate_directions.values()
        )
        if not hints:
            return context
        return replace(
            context,
            incomplete_plans=_unique_text((*context.incomplete_plans, *hints)),
        )

    def candidate_direction_count(self) -> int:
        return len(self._candidate_directions)

    def _has_equivalent_official_direction(
        self,
        direction_id: str,
        label: str,
    ) -> bool:
        if direction_id in self._directions:
            return True
        return any(
            _semantic_relation_score(label, direction.label) >= 0.72
            for direction in self._directions.values()
        )

    def _find_candidate_key(self, direction_id: str, label: str) -> str | None:
        if direction_id in self._candidate_directions:
            return direction_id
        for key, candidate in self._candidate_directions.items():
            if _semantic_relation_score(label, candidate.label) >= 0.72:
                return key
        return None

    def _remove_equivalent_candidate(self, direction_id: str, label: str) -> None:
        candidate_key = self._find_candidate_key(direction_id, label)
        if candidate_key is not None:
            del self._candidate_directions[candidate_key]

    def _text_has_official_direction(self, text: str) -> bool:
        return any(
            _semantic_relation_score(
                text,
                f"{direction.direction_id} {direction.label}",
            )
            >= 0.45
            for direction in self._directions.values()
        )

    def _best_candidate_key_for_text(self, text: str) -> str | None:
        ranked = [
            (
                _semantic_relation_score(
                    text,
                    f"{candidate.direction_id} {candidate.label}",
                ),
                key,
            )
            for key, candidate in self._candidate_directions.items()
        ]
        if not ranked:
            return None
        score, key = max(ranked)
        return key if score >= 0.45 else None

    #只吸收在未修改初始工作区上完成的成功读取结果，防止分支局部文件状态污染兄弟分支
    def absorb_read_only_transition(
        self,
        context: StructuredContext,
        outcome: ExecutionOutcome,
    ) -> bool:
        unchanged_root = (
            outcome.commands_succeeded
            and outcome.parent_snapshot.fingerprint == self.root_fingerprint
            and outcome.resulting_snapshot.fingerprint == self.root_fingerprint
        )
        if not unchanged_root:
            return False

        action_dependencies = _command_workspace_dependencies(outcome)
        scoped_facts = tuple(
            item
            if item.observed_at_fingerprint
            else replace(
                item,
                workspace_dependencies=_fact_workspace_dependencies(
                    item,
                    outcome,
                    action_dependencies,
                ),
                observed_at_fingerprint=outcome.resulting_snapshot.fingerprint,
            )
            for item in context.facts_and_evidence
            if item.verified == "yes"
        )
        changed = False
        old_facts = tuple(self._facts)
        self._facts = list(
            _merge_fact_sequence(
                (*self._facts, *scoped_facts)
            )
        )
        changed = tuple(self._facts) != old_facts
        for item in context.semantic_directions:
            existing = self._directions.get(item.direction_id)
            if existing is None:
                self._directions[item.direction_id] = (
                    replace(
                        item,
                        workspace_dependencies=(
                            item.workspace_dependencies or action_dependencies
                        ),
                        observed_at_fingerprint=(
                            item.observed_at_fingerprint
                            or outcome.resulting_snapshot.fingerprint
                        ),
                    )
                    if item.status == "covered"
                    else item
                )
                changed = True
                continue
            if item.status == "covered":
                merged = replace(
                    item,
                    status="covered",
                    evidence=tuple(dict.fromkeys(existing.evidence + item.evidence)),
                    workspace_dependencies=(
                        item.workspace_dependencies or action_dependencies
                    ),
                    observed_at_fingerprint=(
                        item.observed_at_fingerprint
                        or outcome.resulting_snapshot.fingerprint
                    ),
                )
                if existing != merged:
                    self._directions[item.direction_id] = merged
                    changed = True
        return changed

    #把任务级只读知识注入即将继续搜索的节点；分析结论和文件环境摘要仍保持分支局部
    def enrich(
        self,
        context: StructuredContext,
        *,
        changed_paths_from_root: Iterable[str] = (),
    ) -> StructuredContext:
        #分支局部事实放在前面；同名可变事实优先保留当前分支来源
        changed_paths = _normalized_workspace_paths(changed_paths_from_root)
        valid_shared_facts = tuple(
            item
            for item in self._facts
            if _evidence_is_current(item.workspace_dependencies, changed_paths)
        )
        facts = _merge_fact_sequence((*context.facts_and_evidence, *valid_shared_facts))

        directions = {item.direction_id: item for item in context.semantic_directions}
        for direction_id, shared in self._directions.items():
            earlier = directions.get(direction_id)
            shared_is_current = shared.status != "covered" or _evidence_is_current(
                shared.workspace_dependencies,
                changed_paths,
            )
            if earlier is None:
                directions[direction_id] = (
                    shared
                    if shared_is_current
                    else replace(
                        shared,
                        status="unexplored",
                        evidence=("Previous shared coverage is stale in this workspace state",),
                        workspace_dependencies=(),
                        observed_at_fingerprint="",
                    )
                )
            elif shared.status == "covered" and shared_is_current:
                directions[direction_id] = replace(
                    earlier,
                    status="covered",
                    evidence=tuple(dict.fromkeys(earlier.evidence + shared.evidence)),
                    workspace_dependencies=shared.workspace_dependencies,
                    observed_at_fingerprint=shared.observed_at_fingerprint,
                )
        return replace(
            context,
            facts_and_evidence=facts,
            semantic_directions=tuple(directions.values()),
        )

    def covered_direction_ids(
        self,
        *,
        changed_paths_from_root: Iterable[str] = (),
    ) -> frozenset[str]:
        changed_paths = _normalized_workspace_paths(changed_paths_from_root)
        return frozenset(
            direction_id
            for direction_id, item in self._directions.items()
            if item.status == "covered"
            and _evidence_is_current(item.workspace_dependencies, changed_paths)
        )

    def semantic_coverage_rate(self) -> float:
        if not self._directions:
            return 0.0
        return len(self.covered_direction_ids()) / len(self._directions)

    def core_semantic_coverage_rate(
        self,
        *,
        changed_paths_from_root: Iterable[str] = (),
    ) -> float:
        if not self._core_direction_ids:
            return 0.0
        covered = self.covered_direction_ids(
            changed_paths_from_root=changed_paths_from_root,
        )
        return len(covered & self._core_direction_ids) / len(self._core_direction_ids)

    @property
    def core_direction_ids(self) -> frozenset[str]:
        return frozenset(self._core_direction_ids)


@dataclass(frozen=True, slots=True)
class SemanticCoverageSnapshot:
    covered: int
    total: int

    @property
    def rate(self) -> float:
        return self.covered / self.total if self.total else 0.0


def semantic_coverage_snapshot(
    context: StructuredContext,
    *,
    direction_ids: Iterable[str] | None = None,
) -> SemanticCoverageSnapshot:
    """Return auditable covered/total counts for a dynamic or fixed direction set."""

    directions = {item.direction_id: item for item in context.semantic_directions}
    selected_ids = (
        frozenset(directions)
        if direction_ids is None
        else frozenset(str(item) for item in direction_ids if str(item))
    )
    covered = sum(
        1
        for direction_id in selected_ids
        if direction_id in directions and directions[direction_id].status == "covered"
    )
    return SemanticCoverageSnapshot(covered=covered, total=len(selected_ids))


#默认返回动态发现覆盖率；搜索器显式传入冻结核心方向后得到稳定在线覆盖率。
def semantic_coverage_rate(
    context: StructuredContext,
    *,
    direction_ids: Iterable[str] | None = None,
) -> float:
    return semantic_coverage_snapshot(
        context,
        direction_ids=direction_ids,
    ).rate
''' 
父子节点之间的信息继承
'''
#同一搜索路径中，父节点已经验证的事实必须确定性传给子节点，不能依赖模型是否再次输出
def merge_verified_facts(
    previous: StructuredContext,
    compressed: StructuredContext,
    *,
    semantic_direction_id: str = "",
) -> StructuredContext:
    """Inherit verified facts along one parent-child path without sharing siblings."""

    #父节点只有verified=yes的事实会被强制继承；新事实标注本轮语义来源后统一归并
    inherited = tuple(
        item for item in previous.facts_and_evidence if item.verified == "yes"
    )
    current = tuple(
        replace(item, semantic_direction_id=semantic_direction_id)
        if semantic_direction_id and not item.semantic_direction_id
        else item
        for item in compressed.facts_and_evidence
    )
    return replace(
        compressed,
        facts_and_evidence=_merge_fact_sequence((*inherited, *current)),
    )

#动作生成后，把动作携带的semantic_direction登记到当前上下文；已有方向不重复添加
def register_action_directions(
    context: StructuredContext,
    actions: tuple[MacroAction, ...],
) -> StructuredContext:
    known = {item.direction_id: item for item in context.semantic_directions}
    changed = False
    for action in actions:
        if action.semantic_direction_id not in known:
            known[action.semantic_direction_id] = SemanticDirection(
                direction_id=action.semantic_direction_id,
                label=action.semantic_direction_label,
                status="unexplored",
            )
            changed = True
    return replace(context, semantic_directions=tuple(known.values())) if changed else context

#上下文压缩前后合并语义方向，防止模型压缩时遗漏已经探索过的方向
def merge_semantic_directions(
    previous: StructuredContext,
    compressed: StructuredContext,
) -> StructuredContext:
    """Keep the explicit semantic-space map stable across context compression."""

    merged = {item.direction_id: item for item in previous.semantic_directions}
    for item in compressed.semantic_directions:
        earlier = merged.get(item.direction_id)
        #已经covered的方向不能被后续压缩结果降级，并合并两边的证据
        if earlier is not None and earlier.status == "covered":
            merged[item.direction_id] = replace(
                earlier,
                label=item.label or earlier.label,
                status="covered",
                evidence=tuple(dict.fromkeys(earlier.evidence + item.evidence)),
            )
        elif earlier is not None and not item.observed_at_fingerprint:
            merged[item.direction_id] = replace(
                item,
                workspace_dependencies=earlier.workspace_dependencies,
                observed_at_fingerprint=earlier.observed_at_fingerprint,
            )
        else:
            merged[item.direction_id] = item
    return replace(compressed, semantic_directions=tuple(merged.values()))

#根据本轮执行反馈更新目标语义方向的状态和证据
def set_direction_status(
    context: StructuredContext,
    *,
    direction_id: str,
    label: str,
    status: DirectionStatus,
    evidence: str,
    workspace_dependencies: tuple[str, ...] = (),
    observed_at_fingerprint: str = "",
) -> StructuredContext:
    directions = {item.direction_id: item for item in context.semantic_directions}
    current = directions.get(direction_id)
    #策略可能直接返回一个新方向，因此这里也允许补登记
    if current is None:
        directions[direction_id] = SemanticDirection(
            direction_id=direction_id,
            label=label,
            status=status,
            evidence=(evidence,) if evidence else (),
            workspace_dependencies=(
                workspace_dependencies if status == "covered" else ()
            ),
            observed_at_fingerprint=(
                observed_at_fingerprint if status == "covered" else ""
            ),
        )
    else:
        #covered代表已经获得充分证据，后续失败动作不能把该方向改回failed
        next_status = "covered" if current.status == "covered" else status
        next_evidence = current.evidence + ((evidence,) if evidence and evidence not in current.evidence else ())
        directions[direction_id] = replace(
            current,
            status=next_status,
            evidence=next_evidence,
            workspace_dependencies=(
                workspace_dependencies
                if status == "covered"
                else current.workspace_dependencies
            ),
            observed_at_fingerprint=(
                observed_at_fingerprint
                if status == "covered"
                else current.observed_at_fingerprint
            ),
        )
    return replace(context, semantic_directions=tuple(directions.values()))

#按方向ID查询状态，供事后指标判断某一方向是否已经覆盖
def direction_status(context: StructuredContext, direction_id: str) -> DirectionStatus | None:
    for item in context.semantic_directions:
        if item.direction_id == direction_id:
            return item.status
    return None


def _clip(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    if limit <= 1:
        return compact[:limit]
    return compact[: limit - 1] + "…"


def _json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=list))


def _project_text_items(
    items: tuple[str, ...],
    *,
    budget: int,
    item_limit: int = 480,
) -> list[str]:
    selected: list[str] = []
    #结论、问题和计划通常按时间追加，优先把最近内容交给模型
    for item in reversed(items):
        candidate = _clip(item, item_limit)
        if not candidate or candidate in selected:
            continue
        if _json_chars([candidate, *selected]) > budget:
            continue
        selected.insert(0, candidate)
    return selected


def _project_directions(
    directions: tuple[SemanticDirection, ...],
    *,
    budget: int,
) -> list[dict[str, Any]]:
    #每个方向先保留最小身份和状态，防止压缩破坏语义覆盖空间
    projected = [
        {
            "direction_id": _clip(item.direction_id, 96),
            "label": _clip(item.label, 120),
            "status": item.status,
        }
        for item in directions
    ]
    priority = {"exploring": 3, "failed": 2, "unexplored": 1, "covered": 0}
    ranked = sorted(
        enumerate(directions),
        key=lambda pair: (priority[pair[1].status], pair[0]),
        reverse=True,
    )
    for index, item in ranked:
        if not item.evidence:
            continue
        candidate = dict(projected[index])
        candidate["summary"] = _clip(item.evidence[-1], 360)
        if item.status != "covered":
            evidence = _unique_text(item.evidence[:-1])[-2:]
            if evidence:
                candidate["evidence"] = [_clip(value, 280) for value in evidence]
        previous = projected[index]
        projected[index] = candidate
        if _json_chars(projected) > budget:
            projected[index] = previous
    return projected


def _project_facts(
    facts: tuple[EvidenceItem, ...],
    *,
    active_direction_ids: frozenset[str],
    budget: int,
) -> list[dict[str, Any]]:
    ranked = sorted(
        enumerate(facts),
        key=lambda pair: (
            pair[1].semantic_direction_id in active_direction_ids,
            _VERIFICATION_RANK[pair[1].verified],
            pair[0],
        ),
        reverse=True,
    )
    selected: list[tuple[int, dict[str, Any]]] = []
    for index, item in ranked:
        payload: dict[str, Any] = {
            "claim": _clip(item.claim, 420),
            "source": _clip(item.source, 240),
            "verified": item.verified,
        }
        if item.semantic_direction_id:
            payload["semantic_direction_id"] = _clip(item.semantic_direction_id, 96)
        if item.supporting_sources:
            payload["supporting_source"] = _clip(item.supporting_sources[-1], 180)
        candidate = [value for _, value in selected] + [payload]
        if _json_chars(candidate) <= budget:
            selected.append((index, payload))
    #最终仍按事实进入路径的顺序展示，便于模型理解时间关系
    selected.sort(key=lambda pair: pair[0])
    return [value for _, value in selected]


def _shrink_prompt_payload(payload: dict[str, Any], max_chars: int) -> None:
    """Last-resort structural shrinking; semantic direction identities are never dropped."""

    while _json_chars(payload) > max_chars and payload["facts_and_evidence"]:
        payload["facts_and_evidence"].pop(0)
    for key in ("analysis_and_conclusions", "incomplete_plans", "unresolved_issues"):
        while _json_chars(payload) > max_chars and len(payload[key]) > 1:
            payload[key].pop(0)
    if _json_chars(payload) > max_chars:
        for direction in payload["semantic_directions"]:
            direction.pop("evidence", None)
            if direction.get("status") == "covered":
                direction.pop("summary", None)
    while _json_chars(payload) > max_chars and payload["analysis_and_conclusions"]:
        payload["analysis_and_conclusions"].pop(0)
    while _json_chars(payload) > max_chars and payload["incomplete_plans"]:
        payload["incomplete_plans"].pop(0)
    if _json_chars(payload) > max_chars:
        for direction in payload["semantic_directions"]:
            direction.pop("summary", None)
    while _json_chars(payload) > max_chars and payload["unresolved_issues"]:
        payload["unresolved_issues"].pop(0)
    #通常不会到这里；极端长字符串按字段逐步收紧，仍保留目标、当前解和所有方向
    for limit in (700, 400, 220, 120):
        if _json_chars(payload) <= max_chars:
            break
        payload["task_goal"] = _clip(payload["task_goal"], limit)
        payload["current_solution"] = _clip(payload["current_solution"], limit)
        payload["environment_summary"] = _clip(payload["environment_summary"], limit)
        for direction in payload["semantic_directions"]:
            direction["direction_id"] = _clip(direction["direction_id"], min(limit, 72))
            direction["label"] = _clip(direction["label"], min(limit, 80))


def project_context_for_prompt(
    context: StructuredContext,
    *,
    max_chars: int = 14_000,
) -> dict[str, Any]:
    """Create a bounded model-facing view without mutating the complete checkpoint state."""

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    active_direction_ids = frozenset(
        item.direction_id
        for item in context.semantic_directions
        if item.status != "covered"
    )
    payload: dict[str, Any] = {
        "task_goal": _clip(context.task_goal, max(120, int(max_chars * 0.07))),
        "current_solution": _clip(
            context.current_solution,
            max(160, int(max_chars * 0.15)),
        ),
        "facts_and_evidence": _project_facts(
            context.facts_and_evidence,
            active_direction_ids=active_direction_ids,
            budget=max(200, int(max_chars * 0.18)),
        ),
        "analysis_and_conclusions": _project_text_items(
            context.analysis_and_conclusions,
            budget=max(120, int(max_chars * 0.08)),
        ),
        "unresolved_issues": _project_text_items(
            context.unresolved_issues,
            budget=max(120, int(max_chars * 0.09)),
        ),
        "incomplete_plans": _project_text_items(
            context.incomplete_plans,
            budget=max(120, int(max_chars * 0.07)),
        ),
        "semantic_directions": _project_directions(
            context.semantic_directions,
            budget=max(300, int(max_chars * 0.22)),
        ),
        "environment_summary": _clip(
            context.environment_summary,
            max(120, int(max_chars * 0.08)),
        ),
    }
    _shrink_prompt_payload(payload, max_chars)
    return payload
