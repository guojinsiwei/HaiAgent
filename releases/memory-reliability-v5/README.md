# BestFGS 记忆可靠性 v5

基于独立 v4，修复真实六题实验中经验无法入库及记忆有效性/检索/使用链路问题。
不修改旧 trial、旧源码发布或评分；HAI 的 21 个 Python 源文件与 v4 一致。

## 已确认问题及修正

上次真实六题 BestFGS 仅提出两条记忆，两条分别因 operation 长 123、143 字符超过
120 字符限制而整条被拒。四题没有提出记忆，六题入库/曝光/干预都为零。

v5 对超长的可选 operation / next_step 采用明确的降级：省略该可选字段，保留核心结论、
条件、证据和目标；记录原长度、SHA-256、修正事件并通知主模型。原候选留在审计中。
不截出半条操作规则，也不放松核心字段、证据 ID、类型和路径校验。

`replay_memory.py` 已将真实两条候选重放：**2/2 入库**，结论/条件/证据保持原值。
旧日志没有执行时文件版本，重放记录明确为需复查，不伪造“仍然有效”，不执行历史命令，
不改变历史 reward。原审计位置和哈希在 `evidence/previous-rejected-candidates.json`。

## 借鉴 HAI 的部分

参考 `haiagent/runtime.py` 的执行前后文件版本记录，以及 `terminal_context/core.py` 的
observe、current_query、match_action 和后续结果追踪；未复制 HAI 的停滞退出或硬性封禁。

1. **事件观察记忆**：相同命令、相同完整失败输出在同一工作区重复后，直接记录观察事实；
   公开测试命令退出 0 记录为 finding，不推断整体通过或因果原因。grep/rg 无匹配不当失败，
   截断输出不用于自动重复事实。无模型调用也可生成，受 24 条存储容量约束。
2. **执行时依赖**：记录工具执行前后选定路径的版本。历史证据中的文件锚点不能用今天的
   文件版本替代。无关修改不自动使有依赖锚点的记忆过期；相关依赖变化、未知或链接版本
   不可靠时要求复查。没有文件锚点的经验仍保守依赖工作区版本。
3. **问题驱动检索**：查询包含任务片段、近期命令、错误/输出、动作目的和 Monitor 建议；
   词汇无交集不硬凑四条，相关候选先按适用性排序。当前仍是结构化与词汇检索，非语义向量库。
4. **更窄的动作提醒**：finding/procedure 不作为阻塞性提醒，仅 blocker 可匹配。
   目标文件重合不再单独触发提醒；观察型 blocker 按实际命令身份匹配（含 cwd/stdin）。
   首次匹配时，仅 uses_memory 不足以跳过提醒，需 memory_reason 说明重试理由。
   仍允许重试且同一工作区同一记忆只提醒一次，不无限阻塞。
5. **后续结果核对**：自报使用和提醒均接到后续工具结果。明确引用的观察记忆若再次出现
   相同命令/输出失败且工作区未变，记录 `memory_retry_no_new_outcome` 并请求语义复核；
   它不是自动停止条件，不把改命令或改文件当作收益证明。
6. **保留和配额**：相同结论/条件/依赖合并证据，记录强化次数；按适用性、有限强化次数和
   更新顺序淘汰，而非只按入库先后。最多 32 个关键事件暂存，Monitor 可带入最多 4 个
   窗口外事件。默认 12 次 Monitor 配额有一半保留至工具/时间任一预算过半，未增加总调用数。

## 边界

- 事实与推断分开：程序观察标为 `observed_tool_outcome_not_causal_rule`；Monitor 结论仍标为
  `evidence_quoted_model_claim_not_verified`。原文匹配不等于自然语言结论被证明。
- 依赖仅覆盖保守提取的文件路径（每次最多 16 个）；动态载入文件、服务、网络和包状态
  不保证完整。缺失或冲突的版本保留 unknown，不据此作硬性执行许可/禁止判断。
- Shell 路径提取不执行 Shell、不展开变量；隐藏测试、越界路径被排除。Docker 的范围和
  文件版本尽量合并检查，减少额外进程开销，但仍有文件哈希成本，正式任务需观察其占比。
- 队列、记忆容量和模型上下文均有上限；队列过期、记忆淘汰、检索结果和字段修正均留事件。
- 只做任务内记忆；不做未经验证的跨任务规则迁移、自动矛盾裁决或自动回退。

## 使用与消融

本发布 CLI 和 `integration/transport.py` 默认 `memory_reliability=True`，同时继承 v4 的
semantic_monitor / auto_memory 默认开启。底层 `LeanConfig()` 为保持旧行为默认关闭，
代码集成需显式开启；自动记忆仍需提供独立 monitor_client（即使本次只触发观察型记忆）。

```sh
PYTHONPATH=sources/bestfgs-project/src python -m bestfgs.lean_cli \
  --workspace /path/to/disposable-task --run-root /path/to/new-run \
  --model MODEL_ID --goal '任务要求'
```

- `--no-memory-reliability`：关闭依赖追踪、观察型记忆、新检索/提醒、后半程配额保留等 v5 机制；
  可选字段过长修复仍保留，作为工程修复而非算法消融。
- `--no-auto-memory`：关闭观察型及 Monitor 自动入库，保留 Actor 主动记忆。
- `--no-semantic-monitor`：关闭语义停滞干预；仍可生成自动记忆。
- 默认 Monitor 复用解题模型型号但独立短上下文。`--monitor-model` 可选择同服务的小模型；
  不同服务还可指定 `--monitor-provider`、`--monitor-base-url`、`--monitor-api-key-env`。

新的正式试验必须新建目录，加载 sources 和 integration 覆盖文件，并封存模型、预算、
开关与源码清单。本目录是独立发布和验收目录，不代表已启动正式六题重测。

## 验证与后续

`verify_release.py` 完整回归、`replay_memory.py` 真实候选重放、`cloud_suite.py` 真实 Docker
验收；详见 `VALIDATION.md`。模型均为测试替身，不证明真实任务分数已提升。

下一步固定模型、题目和总预算比较 v4 与 v5；检查候选/拒绝原因、检索、后续重复失败、
成本及最终得分。不能以记忆条数或曝光次数代替收益，也不能把开发六题的提升当泛化结论。
