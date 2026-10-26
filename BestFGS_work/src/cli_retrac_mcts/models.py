from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal
#此文件规定了各种各样的数据结构
#SearchNode=StructuredContext+Environment
'''
SearchNode ──MacroAction──>ExecutionOutcome ──模型理解──>TransitionUpdate  ──创建──>新的 SearchNode
'''

DirectionStatus = Literal["unexplored", "exploring", "covered", "failed"]
ActionIntent = Literal["explore", "candidate"]

''' 一些辅助函数'''
#模型服务或结构化输出在全部重试后仍不可用；MCTS可捕获它并保留已有搜索成果
class ModelCallError(RuntimeError):
    pass

#hashlib.sha256:计算哈希值截取前16为
def stable_id(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"

#uuid：看作随机数生成器
def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"

'''描述任务本身 '''
#任务规范class：任务id、目标、成功的标准/界限、限制
#类装饰器， 不可变对象，    用于内存优化与性能提升
@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    goal: str
    success_criteria: tuple[str, ...] = ()  #criteria:标准、尺度
    constraints: tuple[str, ...] = ()

    #类方法的第一个参数cls：dataclass库特有，等价于this指针
    @classmethod
    def create(
        cls,
        goal: str,
        success_criteria: tuple[str, ...] = (),
        constraints: tuple[str, ...] = (),
    ) -> "TaskSpec":
        return cls(new_id("task"), goal, success_criteria, constraints)

    @property
    def required_success_criteria(self) -> tuple[str, ...]:
        """Return the explicit criteria, falling back to the goal for API callers."""

        return self.success_criteria or (self.goal,)
""" 服务于结构化上下文"""
#证据项，断言/假设、证据来源、是否经过验证
@dataclass(frozen=True, slots=True)
class EvidenceItem:
    claim: str
    source: str
    verified: Literal["yes", "no", "partial"] = "partial"
    #新事实由哪个语义方向产生；用于只在同一语义区域内合并近似表述
    semantic_direction_id: str = ""
    #完整上下文保留合并前的其他来源和表述，模型视图再做有界投影
    supporting_sources: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    #程序根据真实CLI动作绑定的工作区依赖；"*"表示证据依赖整个工作区。
    #这两个字段是运行时溯源信息，不要求模型生成。
    workspace_dependencies: tuple[str, ...] = ()
    observed_at_fingerprint: str = ""
''' 服务于结构化上下文'''
#语义方向：方向id、可读标签/名称、当前探索状态、证据
@dataclass(frozen=True, slots=True)
class SemanticDirection:
    """One explicit region/direction in the task's semantic exploration space."""

    direction_id: str
    label: str
    status: DirectionStatus = "unexplored"
    evidence: tuple[str, ...] = ()
    #covered状态所依据的文件范围和观察时的环境指纹，由运行时维护。
    workspace_dependencies: tuple[str, ...] = ()
    observed_at_fingerprint: str = ""
''' 结构化的上下文，记录智能体当前的认知状态'''
#结构化上下文，最重要
#属性：当前任务目标、当前推导出的解/答案、事实与证据、分析与结论、
#     未解决问题/阻碍、未执行完毕的计划（部分已经执行）、语义方向、环境摘要
@dataclass(frozen=True, slots=True)
class StructuredContext:
    task_goal: str
    current_solution: str = "None"
    facts_and_evidence: tuple[EvidenceItem, ...] = ()
    analysis_and_conclusions: tuple[str, ...] = ()
    unresolved_issues: tuple[str, ...] = ()
    incomplete_plans: tuple[str, ...] = ()
    semantic_directions: tuple[SemanticDirection, ...] = ()
    environment_summary: str = ""

    #生成状态指纹，方便MCTS的不同路径达到完全相同的状态时进行状态合并
    def fingerprint(self) -> str:
        return stable_id("ctx", asdict(self))

    #序列化，对象（结构化上下文）->字典
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    #反序列化，字典->对象
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructuredContext":
        payload = dict(data)
        payload["facts_and_evidence"] = tuple(
            item if isinstance(item, EvidenceItem) else EvidenceItem(
                claim=str(item["claim"]),
                source=str(item["source"]),
                verified=item.get("verified", "partial"),
                semantic_direction_id=str(item.get("semantic_direction_id", "")),
                supporting_sources=tuple(item.get("supporting_sources", ())),
                aliases=tuple(item.get("aliases", ())),
                workspace_dependencies=tuple(item.get("workspace_dependencies", ())),
                observed_at_fingerprint=str(item.get("observed_at_fingerprint", "")),
            )
            for item in payload.get("facts_and_evidence", ())
        )
        payload["semantic_directions"] = tuple(
            item if isinstance(item, SemanticDirection) else SemanticDirection(
                direction_id=str(item["direction_id"]),
                label=str(item["label"]),
                status=item.get("status", "unexplored"),
                evidence=tuple(item.get("evidence", ())),
                workspace_dependencies=tuple(item.get("workspace_dependencies", ())),
                observed_at_fingerprint=str(item.get("observed_at_fingerprint", "")),
            )
            for item in payload.get("semantic_directions", ())
        )
        for name in ("analysis_and_conclusions", "unresolved_issues", "incomplete_plans"):
            payload[name] = tuple(payload.get(name, ()))
        return cls(**payload)
'''
 环境的快照、记录真实的工作区状态
StructuredContext = 脑子里的状态
EnvironmentSnapshot = 硬盘上的状态
'''
#环境快照：id、环境的位置（工作目录路径）、指纹、文本概述、元数据
@dataclass(frozen=True, slots=True)
class EnvironmentSnapshot:
    snapshot_id: str
    location: str
    fingerprint: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
''' 单条bash命令'''
#命令规范：命令行中收到的命令以及参数、文本描述、工作目录（默认是当前目录）、超时时间（可选）、需要标准输入（可选）
@dataclass(frozen=True, slots=True)
class CommandSpec:
    argv: tuple[str, ...]
    description: str
    cwd: str = "."
    timeout_seconds: int | None = None
    stdin: str | None = None

    #序列化
    def normalized(self) -> str:
        return json.dumps(
            {"argv": self.argv, "cwd": self.cwd, "stdin": self.stdin},
            ensure_ascii=False,
            sort_keys=True,
        )
''' 
宏观动作，属于语义层面，一条大的动作，由小bash命令组成
一条宏观动作对应MCTS的一条边
'''
#核心：宏动作类，id、名称、采用该动作的理由、关联的语义探索方向的ID、标签、一组cmd、期望的环境效果/产出、在生成该动作时用到的规则的idSet
# 上面的CommandSpec是微观动作，即单挑Terminal cmd，而下面的宏动作是高层符合动作，指Agent
#为达成某一语义探索方向执行的一系列动作
@dataclass(frozen=True, slots=True)
class MacroAction:
    action_id: str
    name: str
    rationale: str
    semantic_direction_id: str
    semantic_direction_label: str
    commands: tuple[CommandSpec, ...]
    verification_commands: tuple[CommandSpec, ...] = ()
    intent: ActionIntent = "explore"
    expected_effect: str = ""
    applied_rule_ids: tuple[str, ...] = ()
    # BestFGS uses these structured declarations to estimate information gain
    # without making a separate LLM-as-judge request.  Values should copy the
    # current unresolved-issue text when possible; the runtime only rewards
    # exact matches against the current structured context.
    target_issue_ids: tuple[str, ...] = ()
    expected_evidence: str = ""

    #create函数，主要作用是根据这些值去生成一个Hash值，即指纹
    @classmethod
    def create(
        cls,
        *,
        name: str,
        rationale: str,
        semantic_direction_id: str,
        semantic_direction_label: str,
        commands: tuple[CommandSpec, ...],
        verification_commands: tuple[CommandSpec, ...] = (),
        intent: ActionIntent = "explore",
        expected_effect: str = "",
        applied_rule_ids: tuple[str, ...] = (),
        target_issue_ids: tuple[str, ...] = (),
        expected_evidence: str = "",
    ) -> "MacroAction":
        if intent not in {"explore", "candidate"}:
            raise ValueError("intent must be 'explore' or 'candidate'")
        action_id = stable_id(
            "action",
            {
                "name": name,
                "direction": semantic_direction_id,
                "intent": intent,
                "commands": [command.normalized() for command in commands],
                "verification_commands": [
                    command.normalized() for command in verification_commands
                ],
                "target_issue_ids": list(target_issue_ids),
                "expected_evidence": expected_evidence,
            },
        )
        return cls(
            action_id,
            name,
            rationale,
            semantic_direction_id,
            semantic_direction_label,
            commands,
            verification_commands,
            intent,
            expected_effect,
            applied_rule_ids,
            target_issue_ids,
            expected_evidence,
        )

    #直接返回该动作的Hash val
    def signature(self) -> str:
        return self.action_id


@dataclass(frozen=True, slots=True)
class InitialSemanticPlan:
    """模型给出的初始语义地图，以及唯一一个立即执行的Bootstrap动作。"""

    semantic_directions: tuple[SemanticDirection, ...]
    bootstrap_action: MacroAction
''' 
下面分别是单条命令执行结束的结果和宏观动作执行的结果，
其中有三种不同判断：
- commands_succeeded：模型要求的普通命令是否成功。
- validation_succeeded：程序自动检查语法、冲突标记等是否通过。
- functional_validation_succeeded：测试、构建或断言是否通过。
workspace_changed则通过前后环境指纹判断文件是否真的被修改。
'''
#整理单条cmd执行后的完整反馈结果：cmd、系统的返回码（0）、期间产生的标准输出/报错、耗费的时间、是否超时与被拦截过
@dataclass(frozen=True, slots=True)
class CommandResult:
    command: CommandSpec
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    blocked: bool = False

    #判断命令是否执行成功
    @property
    def succeeded(self) -> bool:
        return not self.blocked and not self.timed_out and self.return_code == 0

#执行某宏观动作后的环境反馈：执行前的环境快照、执行后的环境快照、执行的宏动作对象、该宏动作包含的所有底层cmd的执行结果集合、动作开始的时间戳
@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    parent_snapshot: EnvironmentSnapshot
    resulting_snapshot: EnvironmentSnapshot
    action: MacroAction
    command_results: tuple[CommandResult, ...]
    started_at: float = field(default_factory=time.time)
    #环境在修改完成后自动执行的确定性门槛，不计入模型工具调用预算
    validation_results: tuple[CommandResult, ...] = ()
    #由动作显式声明的功能验证命令；与内部语法门槛分开，并计入工具调用
    functional_validation_results: tuple[CommandResult, ...] = ()
    # The search runtime supplies the immutable task root for cumulative audits.
    audit_baseline_snapshot: EnvironmentSnapshot | None = None

    #工具调用计数、
    @property
    def tool_call_count(self) -> int:
        return len(self.command_results) + len(self.functional_validation_results)

    #是否所有工具都执行成功
    @property
    def commands_succeeded(self) -> bool:
        return bool(self.command_results) and all(result.succeeded for result in self.command_results)

    @property
    def validation_succeeded(self) -> bool:
        return all(result.succeeded for result in self.validation_results)

    @property
    def functional_validation_attempted(self) -> bool:
        return bool(self.functional_validation_results)

    @property
    def functional_validation_succeeded(self) -> bool:
        return bool(self.functional_validation_results) and all(
            result.succeeded for result in self.functional_validation_results
        )

    #父子快照文件树指纹不同，说明该动作改变了工作区；这是分支隔离状态，不是研究指标
    @property
    def workspace_changed(self) -> bool:
        return self.parent_snapshot.fingerprint != self.resulting_snapshot.fingerprint

    @property
    def changed_workspace_paths(self) -> tuple[str, ...]:
        """Return deterministic parent-to-child file changes, or a safe wildcard.

        Real forked workspaces populate this metadata. Lightweight/custom
        environments without a file manifest remain compatible and report no
        path-level invalidation because their fingerprints may represent
        non-file state.
        """

        raw = self.resulting_snapshot.metadata.get("changed_paths_from_parent")
        if isinstance(raw, (list, tuple)):
            return tuple(str(item) for item in raw if str(item))
        return ()

    #执行细节生成观察文本
    def observation_text(self) -> str:
        parts: list[str] = []
        for result in (
            self.command_results
            + self.validation_results
            + self.functional_validation_results
        ):
            parts.append(
                "\n".join(
                    [
                        f"COMMAND: {result.command.description}",
                        f"ARGV: {list(result.command.argv)}",
                        f"RETURN_CODE: {result.return_code}",
                        f"STDOUT:\n{result.stdout}",
                        f"STDERR:\n{result.stderr}",
                    ]
                )
            )
        return "\n\n".join(parts)
''' 状态转移相关的两个数据结构'''
#状态转移评估：状态分为：探索中、已经覆盖、失败；、任务是否成功、反馈
@dataclass(frozen=True, slots=True)
class TransitionAssessment:
    direction_status: Literal["exploring", "covered", "failed"]
    #task_success只保留模型的主观声明，不能直接控制停止。
    task_success: bool
    feedback: str
    #模型只能报告它认为由本轮观测支持的标准；这些字段只用于诊断。
    satisfied_success_criteria: tuple[str, ...] = ()
    #candidate_success由真实修改、基础门槛和功能测试确定。
    candidate_success: bool = False
    #独立证据审计器的判定；off表示未启用，unavailable表示调用失败。
    judge_verdict: Literal[
        "off", "pass", "fail", "insufficient_evidence", "unavailable"
    ] = "off"
    judge_summary: str = ""
    #只有运行时硬门槛和启用的独立审计均通过时才允许为True。
    verified_success: bool = False

#一次模型请求同时返回转移判断和下一节点上下文，避免重复发送同一份CLI观测
@dataclass(frozen=True, slots=True)
class TransitionUpdate:
    assessment: TransitionAssessment
    next_context: StructuredContext
'''和奖励相关的数据结构'''
#奖励明细：总奖励、语义覆盖变化量、任务成功奖励
@dataclass(frozen=True, slots=True)
class RewardBreakdown:
    total: float
    semantic_coverage_delta: float
    task_success_reward: float

#状态转移记录类，保存一条MCTS边执行前后的全部信息，供回传、GRPO和事后指标共同使用
@dataclass(frozen=True, slots=True)
class TransitionRecord:
    task_id: str
    iteration: int
    parent_node_id: str
    child_node_id: str
    action: MacroAction
    outcome: ExecutionOutcome
    assessment: TransitionAssessment
    reward: RewardBreakdown
    state_before: StructuredContext
    state_after: StructuredContext
    semantic_coverage_before: float
    semantic_coverage_after: float
    #动态发现覆盖率保留全部运行中新加入的方向，用于诊断地图扩张；
    #上面两个字段改为固定核心方向覆盖率，供在线奖励和阶段切换使用。
    discovered_semantic_coverage_before: float = 0.0
    discovered_semantic_coverage_after: float = 0.0
"""
核心：
  结构化上下文 + 环境快照
辅助计算的：
  访问次数 visits
  累计价值 total_value
retrac的：
  待执行动作 pending_actions
  已尝试动作 tried_action_ids
拓扑关系：
  父节点和出边
"""
#搜索节点：结构化上下文+环境快照，并记录访问次数、累计价值、待尝试动作和父子关系
@dataclass(slots=True)
class SearchNode:
    """A compressed RE-TRAC state and its isolated CLI snapshot."""

    node_id: str
    context: StructuredContext
    snapshot: EnvironmentSnapshot
    visits: int = 0
    total_value: float = 0.0
    terminal: bool = False    #是否为终局状态
    parent_ids: set[str] = field(default_factory=set)
    outgoing_edge_ids: list[str] = field(default_factory=list)   #通往子节点的边的id列表
    pending_actions: list[MacroAction] = field(default_factory=list) #待尝试宏动作
    tried_action_ids: set[str] = field(default_factory=set)  #已经尝试过的宏动作id集合
    expansion_batches: int = 0  #执行扩展批次的计数器
    applicable_rule_ids: tuple[str, ...] = ()  #适用规则的元组
    exhausted: bool = False  #该节点已经没有待执行动作或可到达的未耗尽子节点

    #节点平均价值Q，总价值除以访问次数；未访问时取0  MCTS的重要依据
    @property
    def mean_value(self) -> float:
        return self.total_value / self.visits if self.visits else 0.0

    #上下文指纹和环境指纹共同组成状态key，用来判断两个分支是否到达同一状态
    def state_key(self) -> str:
        return stable_id(
            "state",
            {"context": self.context.fingerprint(), "environment": self.snapshot.fingerprint},
        )
"""
起点、终点、MacroAction
执行动作后的语义覆盖率
访问次数和累计价值
"""
#搜索边：表示从父节点执行一个宏动作到达子节点，同时保存UCB需要的统计量
@dataclass(slots=True)
class SearchEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    action: MacroAction
    semantic_coverage_rate: float   #通过该动作转移后达到的语义覆盖率
    visits: int = 0
    total_value: float = 0.0
'''
主要做三件事：
1. add_root()：建立根节点。
2. update_context()：节点上下文变化后更新索引。
3. add_or_merge_child()：添加子节点或合并等价节点。
'''
'''
现在的合并顺序：
  先检查上下文和环境是否完全相同
          ↓
  再限定到相同环境指纹的节点
          ↓
  调用semantic.py判断结构化语义是否等价
          ↓
  等价则复用节点并合并证据
'''
#搜索图：统一保存所有节点和边，并通过state_index支持相同状态合并
@dataclass(slots=True)
class SearchGraph:
    """Search graph kept with the rest of the shared MCTS data model."""

    nodes: dict[str, SearchNode] = field(default_factory=dict)
    edges: dict[str, SearchEdge] = field(default_factory=dict)
    state_index: dict[str, str] = field(default_factory=dict)  #状态与idx映射表，方便去重与合并
    #语义合并只能在完全相同的环境指纹桶内进行；列表保持节点插入顺序，保证可复现。
    environment_index: dict[str, list[str]] = field(default_factory=dict)
    root_node_id: str | None = None

    #根据任务初始上下文和初始环境快照创建根节点
    def add_root(self, context: StructuredContext, snapshot: EnvironmentSnapshot) -> SearchNode:
        node = SearchNode(new_id("node"), context, snapshot)
        self.nodes[node.node_id] = node
        self.state_index[node.state_key()] = node.node_id
        self.environment_index.setdefault(snapshot.fingerprint, []).append(node.node_id)
        self.root_node_id = node.node_id
        return node

    #节点上下文变化时同步更新state_index，否则旧指纹会失效
    def update_context(self, node: SearchNode, context: StructuredContext) -> None:
        self.state_index.pop(node.state_key(), None)
        node.context = context
        self.state_index[node.state_key()] = node.node_id

    #增加子节点；如果上下文和环境都相同，则复用已有节点而不是重复建树
    def add_or_merge_child(
        self,
        *,
        parent: SearchNode,
        context: StructuredContext,
        snapshot: EnvironmentSnapshot,
        action: MacroAction,
        terminal: bool,
        semantic_coverage_rate: float,
        applicable_rule_ids: tuple[str, ...],
        context_merger: Callable[
            [StructuredContext, StructuredContext], StructuredContext | None
        ] | None = None,
    ) -> tuple[SearchNode, SearchEdge, bool]:
        #先生成备选节点
        candidate = SearchNode(
            new_id("node"),
            context,
            snapshot,
            terminal=terminal,
            parent_ids={parent.node_id},
            applicable_rule_ids=applicable_rule_ids,
        )
        key = candidate.state_key()
        #系统拿着这个Hash值去查字典
        merged = key in self.state_index
        if merged:#放弃候选节点
            child = self.nodes[self.state_index[key]]
            child.parent_ids.add(parent.node_id)
            child.terminal = child.terminal or terminal
            child.applicable_rule_ids = tuple(
                dict.fromkeys((*child.applicable_rule_ids, *applicable_rule_ids))
            )
        elif context_merger is not None:
            child = candidate
            merged_context: StructuredContext | None = None
            for node_id in self.environment_index.get(snapshot.fingerprint, ()):
                existing = self.nodes[node_id]
                merged_context = context_merger(existing.context, context)
                if merged_context is not None:
                    child = existing
                    break
            if merged_context is not None:
                if merged_context != child.context:
                    self.update_context(child, merged_context)
                child.parent_ids.add(parent.node_id)
                child.terminal = child.terminal or terminal
                child.applicable_rule_ids = tuple(
                    dict.fromkeys((*child.applicable_rule_ids, *applicable_rule_ids))
                )
                child.exhausted = child.terminal
                merged = True
            else:
                self.nodes[child.node_id] = child
                self.state_index[key] = child.node_id
                self.environment_index.setdefault(snapshot.fingerprint, []).append(
                    child.node_id
                )
        else:
            child = candidate
            self.nodes[child.node_id] = child
            self.state_index[key] = child.node_id
            self.environment_index.setdefault(snapshot.fingerprint, []).append(
                child.node_id
            )
        #决定是否合并节点后再加边
        edge = SearchEdge(
            new_id("edge"),
            parent.node_id,
            child.node_id,
            action,


            semantic_coverage_rate,
        )
        self.edges[edge.edge_id] = edge
        parent.outgoing_edge_ids.append(edge.edge_id)
        parent.tried_action_ids.add(action.signature())
        return child, edge, merged

    #返回根节点；搜索尚未初始化时直接报错
    def root(self) -> SearchNode:
        if self.root_node_id is None:
            raise RuntimeError("graph has no root")
        return self.nodes[self.root_node_id]
