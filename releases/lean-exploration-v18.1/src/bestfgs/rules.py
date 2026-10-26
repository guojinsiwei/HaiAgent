from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Literal

from .models import MacroAction, StructuredContext, new_id

'''
把单任务多轮交互中的经验整理为 recommend 和 avoid 两类规则。
规则保存适用条件、语义方向、动作特征、命令签名和证据，
筛选经验：先利用语义相似度选出一部分，然后做top-k
avoid 规则可过滤明显重复或已知失败的动作，recommend 规则既进入模型提示，也能成为BestFGS优先级证据。
'''
#任务经验只整理为两类规则：成功经验推荐复用，失败经验避免重复
RuleKind = Literal["recommend", "avoid"]
FailureKind = Literal[
    "none",
    "command_syntax",
    "path_error",
    "tool_missing",
    "environment_error",
    "duplicate_action",
    "strategy_failure",
    "semantic_conflict",
]
RuleScope = Literal["exact_command", "exact_action", "semantic_strategy"]
SharingScope = Literal["task", "environment"]


@dataclass(frozen=True, slots=True)
class RuleApplication:
    """Deterministic runtime effect of task-local RE-TRAC experience."""

    blocked: bool
    recommend_rule_ids: tuple[str, ...] = ()
    avoided_rule_ids: tuple[str, ...] = ()


#规则保存适用条件和语义意图；action_name仅用于兼容精确匹配快速通道
@dataclass(frozen=True, slots=True)
class TaskRule:
    rule_id: str
    task_id: str
    kind: RuleKind
    semantic_direction_id: str
    action_name: str
    evidence: tuple[str, ...] = ()
    semantic_direction_label: str = ""
    condition: str = ""
    guidance: str = ""
    failure_kind: FailureKind = "none"
    scope: RuleScope = "semantic_strategy"
    action_signature: str = ""
    command_signatures: tuple[str, ...] = ()
    # task 经验可跨本任务的全部搜索分支迁移；environment 经验只在文件树指纹
    # 相同的分支间共享，避免把某个候选补丁上的试错结论错误套到其他代码状态。
    sharing_scope: SharingScope = "task"
    applicable_environment_fingerprints: tuple[str, ...] = ()
    # Optional conditioned-experience provenance; legacy stores leave these empty.
    evidence_ids: tuple[str, ...] = ()
    experience_kind: str = ""
    condition_status: str = "unknown"
    dependency_paths: tuple[str, ...] = ()
    hard_block_eligible: bool = False
    counterexample_guidance: str = ""
    # v8 active micro-memory view. The complete source list remains in the
    # task-local audit; none of these annotations confers a priority bonus.
    micro_experience_id: str = ""
    source_count: int = 1
    operation: str = ""
    target_paths: tuple[str, ...] = ()
    premises: tuple[dict, ...] = ()
    match_reasons: tuple[str, ...] = ()
    source_validity: str = "unknown"

    #召回只比较语义摘要，不把完整历史轨迹重新放回模型上下文
    def retrieval_text(self) -> str:
        return " ".join(
            item
            for item in (
                self.semantic_direction_id,
                self.semantic_direction_label,
                self.condition,
                self.guidance,
                self.failure_kind,
                self.scope,
                " ".join(self.evidence),
            )
            if item
        )


#每次任务创建一个新仓库，多轮搜索结束后随任务结果一起返回
@dataclass(slots=True)
class TaskRuleStore:
    task_id: str
    _rules: list[TaskRule] = field(default_factory=list)

    def _check_task(self, task_id: str) -> None:
        if task_id != self.task_id:
            raise ValueError(f"rule scope violation: store={self.task_id}, request={task_id}")

    #相同方向、动作、类型和适用条件的经验合并证据，不重复创建规则
    def add(
        self,
        *,
        task_id: str,
        kind: RuleKind,
        semantic_direction_id: str,
        action_name: str,
        evidence: str,
        semantic_direction_label: str = "",
        condition: str = "",
        guidance: str = "",
        failure_kind: FailureKind = "strategy_failure",
        scope: RuleScope = "semantic_strategy",
        action_signature: str = "",
        command_signatures: tuple[str, ...] = (),
        sharing_scope: SharingScope = "task",
        applicable_environment_fingerprints: tuple[str, ...] = (),
    ) -> TaskRule:
        self._check_task(task_id)
        if kind == "recommend":
            failure_kind = "none"
            scope = "semantic_strategy"
        if failure_kind not in {
            "none", "command_syntax", "path_error", "tool_missing",
            "environment_error", "duplicate_action", "strategy_failure",
            "semantic_conflict",
        }:
            raise ValueError(f"unsupported failure kind: {failure_kind}")
        if scope not in {"exact_command", "exact_action", "semantic_strategy"}:
            raise ValueError(f"unsupported rule scope: {scope}")
        if sharing_scope not in {"task", "environment"}:
            raise ValueError(f"unsupported sharing scope: {sharing_scope}")
        applicable_environment_fingerprints = tuple(
            dict.fromkeys(
                item for item in applicable_environment_fingerprints if item
            )
        )
        if sharing_scope == "environment" and not applicable_environment_fingerprints:
            raise ValueError(
                "environment-scoped rules require an applicable environment fingerprint"
            )
        if sharing_scope == "task":
            applicable_environment_fingerprints = ()
        for index, rule in enumerate(self._rules):
            same_rule = (
                rule.kind == kind
                and rule.semantic_direction_id == semantic_direction_id
                and rule.action_name.casefold() == action_name.casefold()
                and _normalized_text(rule.condition) == _normalized_text(condition)
                and rule.failure_kind == failure_kind
                and rule.scope == scope
                and rule.action_signature == action_signature
                and rule.command_signatures == command_signatures
                and rule.sharing_scope == sharing_scope
            )
            if same_rule:
                items = rule.evidence
                if evidence and evidence not in items:
                    items += (evidence,)
                updated = replace(
                    rule,
                    evidence=items,
                    semantic_direction_label=(
                        semantic_direction_label or rule.semantic_direction_label
                    ),
                    guidance=guidance or rule.guidance,
                    applicable_environment_fingerprints=tuple(
                        dict.fromkeys(
                            (
                                *rule.applicable_environment_fingerprints,
                                *applicable_environment_fingerprints,
                            )
                        )
                    ),
                )
                self._rules[index] = updated
                return updated
        rule = TaskRule(
            rule_id=new_id("rule"),
            task_id=task_id,
            kind=kind,
            semantic_direction_id=semantic_direction_id,
            action_name=action_name,
            evidence=(evidence,) if evidence else (),
            semantic_direction_label=semantic_direction_label,
            condition=condition,
            guidance=guidance,
            failure_kind=failure_kind,
            scope=scope,
            action_signature=action_signature,
            command_signatures=command_signatures,
            sharing_scope=sharing_scope,
            applicable_environment_fingerprints=(
                applicable_environment_fingerprints
            ),
        )
        self._rules.append(rule)
        return rule

    #先保留当前方向ID的精确候选，再按语义摘要相似度补足Top-k
    def retrieve(
        self,
        *,
        task_id: str,
        context: StructuredContext,
        limit: int,
        environment_fingerprint: str | None = None,
    ) -> tuple[TaskRule, ...]:
        self._check_task(task_id)
        if limit <= 0:
            raise ValueError("rule retrieval limit must be positive")
        if not self._rules:
            return ()

        direction_ids = {
            item.direction_id
            for item in context.semantic_directions
            if item.status != "covered"
        }
        query = _context_retrieval_text(context)
        ranked: list[tuple[bool, float, bool, int, TaskRule]] = []
        for index, rule in enumerate(self._rules):
            if not _rule_is_eligible(rule, environment_fingerprint):
                continue
            exact_direction = rule.semantic_direction_id in direction_ids
            relevance = _semantic_relevance(query, rule.retrieval_text())
            portable = _portable_across_directions(rule)
            #没有精确方向关系也没有语义交集的规则不交给模型，避免退化成全量阅读
            #工具/命令能力和已验证测试配方属于少量高价值任务级经验，允许跨方向进入Top-k。
            if exact_direction or relevance > 0.0 or portable:
                ranked.append((exact_direction, relevance, portable, index, rule))

        ranked.sort(
            key=lambda item: (item[0], item[1], item[2], item[3]),
            reverse=True,
        )
        return tuple(item[4] for item in ranked[:limit])

    # 保留简化接口供轻量策略使用；主搜索会显式传入 Top-k 上限。
    def relevant(self, *, task_id: str, context: StructuredContext) -> tuple[TaskRule, ...]:
        return self.retrieve(task_id=task_id, context=context, limit=5)

    #精确匹配是快速通道；模型从Top-k候选中标注的规则构成语义适用性结果
    def apply(
        self,
        *,
        task_id: str,
        action: MacroAction,
        environment_fingerprint: str | None = None,
    ) -> tuple[bool, tuple[str, ...]]:
        decision = self.evaluate(
            task_id=task_id,
            action=action,
            environment_fingerprint=environment_fingerprint,
        )
        return decision.blocked, decision.recommend_rule_ids

    def evaluate(
        self,
        *,
        task_id: str,
        action: MacroAction,
        environment_fingerprint: str | None = None,
    ) -> RuleApplication:
        """Resolve both positive reuse and explicit failure avoidance.

        Recommend IDs raise search priority.  Avoid IDs identify a newly
        generated alternative that follows a failure rule; identical failed
        commands/actions remain hard-blocked.  This separation prevents an
        action that *repairs* a failed strategy from being mistaken for the
        failed action itself.
        """
        self._check_task(task_id)
        selected_ids = set(action.applied_rule_ids) | set(action.avoided_rule_ids)
        current_command_signatures = {
            command.normalized() for command in action.commands
        }
        selected_matches = tuple(
            rule
            for rule in self._rules
            if rule.rule_id in selected_ids
            and _rule_is_eligible(rule, environment_fingerprint)
        )
        exact_matches = tuple(
            rule
            for rule in self._rules
            if _rule_is_eligible(rule, environment_fingerprint)
            and (
                (
                    rule.action_signature
                    and rule.action_signature == action.signature()
                )
                or (
                    rule.scope == "exact_command"
                    and bool(
                        current_command_signatures.intersection(
                            rule.command_signatures
                        )
                    )
                )
                or (
                    not rule.action_signature
                    and rule.semantic_direction_id == action.semantic_direction_id
                    and rule.action_name.casefold() == action.name.casefold()
                )
            )
        )
        matches_by_id = {
            rule.rule_id: rule for rule in selected_matches + exact_matches
        }

        #召回或模型选择只说明“可能相关”；作用域决定规则是否真的有权硬阻止动作
        blocked = any(
            rule.kind == "avoid"
            and _avoid_blocks_action(
                rule,
                action,
            )
            for rule in matches_by_id.values()
        )
        recommended = tuple(
            rule.rule_id
            for rule in matches_by_id.values()
            if rule.kind == "recommend"
        )
        avoided = tuple(
            rule.rule_id
            for rule in matches_by_id.values()
            if rule.kind == "avoid" and _avoid_guides_alternative(rule, action)
        )
        return RuleApplication(blocked, recommended, avoided)

    def all(self) -> tuple[TaskRule, ...]:
        return tuple(self._rules)


def _avoid_blocks_action(
    rule: TaskRule,
    action: MacroAction,
) -> bool:
    if rule.scope == "exact_command":
        current_commands = {command.normalized() for command in action.commands}
        return bool(current_commands.intersection(rule.command_signatures))
    if rule.scope == "exact_action":
        if rule.action_signature:
            return rule.action_signature == action.signature()
        return (
            rule.semantic_direction_id == action.semantic_direction_id
            and rule.action_name.casefold() == action.name.casefold()
        )
    #语义策略经验继续提供给模型组织动作，但不具有程序级硬阻止权限。
    #只有可复现的相同命令或相同动作才能被avoid规则直接过滤。
    return False


def _avoid_guides_alternative(rule: TaskRule, action: MacroAction) -> bool:
    """Accept an Avoid compliance claim only when it is relevant and non-repeating."""

    if _avoid_blocks_action(rule, action):
        return False
    if rule.semantic_direction_id == action.semantic_direction_id:
        return True
    action_text = " ".join(
        item
        for item in (
            action.semantic_direction_id,
            action.semantic_direction_label,
            action.name,
            action.rationale,
            action.expected_effect,
            action.expected_evidence,
        )
        if item
    )
    return _semantic_relevance(action_text, rule.retrieval_text()) >= 0.15


def _rule_is_eligible(
    rule: TaskRule,
    environment_fingerprint: str | None,
) -> bool:
    if rule.sharing_scope == "task":
        return True
    return bool(
        environment_fingerprint
        and environment_fingerprint in rule.applicable_environment_fingerprints
    )


def _portable_across_directions(rule: TaskRule) -> bool:
    """只放行少量与具体语义方向无关、且可安全迁移的任务级经验。"""

    if rule.sharing_scope != "task":
        return False
    return (
        rule.failure_kind in {"tool_missing", "command_syntax"}
        or rule.action_name.startswith("reuse_functional_verifier")
    )


#当前节点只提供高信噪比状态，避免事实日志把规则召回带偏
def _context_retrieval_text(context: StructuredContext) -> str:
    directions = " ".join(
        f"{item.direction_id} {item.label}"
        for item in context.semantic_directions
        if item.status != "covered"
    )
    return " ".join(
        item
        for item in (
            context.task_goal,
            context.current_solution,
            " ".join(context.unresolved_issues),
            " ".join(context.incomplete_plans),
            directions,
            context.environment_summary,
        )
        if item and item != "None"
    )


#对已经由模型压缩出的语义文本做轻量特征化；不依赖跨任务向量库或新增模型服务
def _semantic_features(text: str) -> Counter[str]:
    normalized = _normalized_text(text).replace("_", " ")
    features: Counter[str] = Counter()
    for token in re.findall(r"[a-z0-9]+", normalized):
        if len(token) >= 2:
            features[f"word:{token}"] += 1
    for sequence in re.findall(r"[\u3400-\u9fff]+", normalized):
        if len(sequence) == 1:
            features[f"cjk:{sequence}"] += 1
            continue
        for size in (2, 3):
            for index in range(max(0, len(sequence) - size + 1)):
                features[f"cjk:{sequence[index:index + size]}"] += 1
    return features


def _semantic_relevance(left: str, right: str) -> float:
    left_features = _semantic_features(left)
    right_features = _semantic_features(right)
    if not left_features or not right_features:
        return 0.0
    common = set(left_features).intersection(right_features)
    dot = sum(left_features[item] * right_features[item] for item in common)
    left_norm = math.sqrt(sum(value * value for value in left_features.values()))
    right_norm = math.sqrt(sum(value * value for value in right_features.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _normalized_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())
