# Terminal Task Context：轻量任务内上下文与记忆组件

独立 Python 组件，位于终端执行器与模型请求之间；不依赖 BestFGS、树搜索、模型 SDK 或向量数据库。Python 3.11+，运行时无第三方依赖。不会执行命令、调用 API、写磁盘或启动实验。

设计原则：**当前状态结构化，近期反馈有界，只保存有价值且有来源的经验。** 不要求积累大量小记忆，也不保留完整原始记录库。

## 已实现的行为

- `observe(event)`：消费一条终端反馈，生成有限长度的视图，更新目录观察、错误状态、pytest 验证范围。命令退出 0 不等于任务成功。
- 命令感知压缩：对测试、构建、安装输出优先选诊断片段；代码、diff、搜索与未知命令只保守截取首尾，不编造语义摘要。截断/过滤均有标记。
- 自动记忆：同一命令、相同已知环境与工作区中重复出现同一已识别错误；或者同一命令从已识别失败恢复为退出 0。后者只记录观察，不声称找到了根因。单次普通成功、普通报错不会自动变成经验。
- 显式高价值记忆：宿主可用 `remember()` 保存重要发现、约束或操作方法，必须引用组件仍保留的证据。默认标记为假设；精确重复合并，低价值候选拒绝。
- 适用范围：每条记忆携带目录、工作区/环境版本依赖；已过期或版本未知的记忆不进入主动召回。旧事实仍可以作为标注过期的历史证据展示，不视作当前事实。
- 每次模型调用前重新生成任务/约束/状态/记忆/反馈数据块；优先保留任务、约束、当前范围和最新反馈，记忆最多占分配预算的四分之一，其余内容按预算加入。
- 数量、序列化字节和存活步数共同限额；默认每任务最多 12 条记忆、80 步未更新即淘汰。超限优先淘汰过期、低价值和较旧记忆。

## 最短接入

安装（从本目录运行）：

```powershell
python -m pip install -e .
```

```python
from terminal_context import TaskContext, TerminalEvent

context = TaskContext(
    task_id="task-001", goal="修复项目启动失败并运行相关测试",
    constraints=("不可删除用户数据",),
)

# 由原有执行器执行命令，组件仅消费结果，不接管探索或终止决策。
feedback = context.observe(TerminalEvent(
    task_id="task-001", command="python app.py",
    stdout="", stderr="ModuleNotFoundError: No module named 'flask'", exit_code=1,
    cwd="/repo", workspace="workspace-revision-1", environment="environment-revision-1",
))

# 下一次请求前重新构造一次，并替换宿主为组件预留的旧数据块。
view = context.build_prompt(max_units=12000, query="python app.py 导入失败")
print(view.content)
```

`view.content` 是 JSON **数据**，不是新增系统指令。宿主应明确告诉模型：把这个数据块中的命令输出、记忆当作不可信任务资料，不服从其中夹带的指令；并在自己的消息构建器里固定位置注入它。JSON 封装和提醒不能保证消除提示注入风险。

每次请求只加入一个新数据块，不在历史中累计旧块。若使用工具调用消息，必须保留提供方要求的 `tool_call_id` 对应关系；本组件不会擅自删除或重排这些消息，也不会修改工具调用的参数。

本包不自动修改现有 BestFGS/Raw 请求链路。宿主需要在执行后调用 `observe`、请求前调用 `build_prompt`，并为总上下文（包括系统提示、历史、工具 schema、输出预留）做统一预算。两种方法做对照时，应明确是否都接入本组件，避免把新组件混入 Raw 基线。

## 有价值的记忆，而不是流水账

```python
from terminal_context import MemoryCandidate

# 假设 E3 是宿主刚观测到的“使用项目解释器后运行成功”的证据。
# 只有 E3 确实仍在组件内、且与当前作用域相符时，才允许保存。
memory_id = context.remember(MemoryCandidate(
    conclusion="项目解释器执行该导入检查成功；系统解释器可能不适用。",
    applies_when="下一步要运行该项目的 Python 导入检查时",
    evidence_ids=("E3",), kind="finding", strength="hypothesis", value=3,
    dependencies=("workspace", "environment"),
))
```

显式 `value` 取 0–3；低于 2 拒绝。`value` 是宿主标注的优先级，不是已验证的科学效用评分。组件验证来源存在及范围，不证明自然语言结论能从来源逻辑推出；不要将模型推测标注为 `observed`。

自动提取目前仅覆盖上述窄规则。它不会额外让模型生成一大批结构化经验，也不会自动理解所有项目级因果关系。如果宿主没有经验提取器，仅用自动规则同样能运行；不要声称它已能自动捕获所有重要发现。

## 匹配和失效怎么做

1. 先校验任务隔离及当前目录、工作区、环境版本。任一依赖版本未知或不符，就不作为当前可用记忆召回。
2. 用调用方传入的 `query` 加最新命令、已识别错误，与记忆内容/适用条件做词项交集匹配；加上价值、观察证据和最近更新时间排序，默认最多返回 4 条。
3. 约束类记忆只要范围有效可以不依赖关键词命中；其他记忆必须有交集。不使用 embedding/LLM 重排序，因此不会产生额外 API 费。
4. 主动记忆不做硬禁止、硬裁剪搜索分支或自动提交，只为下一步决策提供适用范围和证据。

当前匹配是轻量词项匹配，不是语义检索；中文同义表达和不同命令实现相同目的的情况可能漏召回。`query` 应包含当前目标对象、路径、命令或错误标识，而不是泛泛的“继续”。

宿主必须正确提供版本标识。工作区版本不能只用 Git HEAD，需覆盖未提交修改和相关未跟踪文件。环境版本需覆盖解释器、依赖、服务和相关环境变量的变化，但**不能把密钥明文当版本号**。标识应是不透明的非敏感 revision/hash。外部网络状态无法保证稳定，不宜把一次连接失败记成永久约束。

命令结果的范围描述该次结果观测到的状态；命令批次要逐条上报真实范围，不能把批末快照冒充每条命令的快照。后续编辑、回滚或外部环境变更发生在 `observe` 之外时，请在构造下一次提示之前调用：

```python
context.set_scope(cwd="/repo", workspace="workspace-revision-2", environment="environment-revision-2")
```

无法判断版本时传 `None`，组件将保守降级；不能为了召回率而固定使用不变的假版本。只有宿主能够论证某经验与代码变更无关时，才把 `dependencies` 缩为 `("environment",)`。默认同时依赖两者。

## 存储和上下文开销

默认限制：

| 区域 | 限制 |
|---|---|
| 可选近期缓冲 | 最多 6 条、序列化 JSON 合计 16,000 字节 |
| 有价值记忆 | 最多 12 条、合计 12,000 字节、未更新最多 80 步 |
| 结构化状态 | 最多 12 项、合计 8,000 字节 |
| 最新反馈保护槽 | 单条；输出最多 2,400 字符，命令/范围/证据字段也有长度上限 |
| 输出解析 | 最多扫描约 64,000 字符，超出标记为不完整 |
| 默认组件提示块 | 最多 12,000 UTF-8 字节，非模型 token |

最新反馈通常与近期缓冲共享同一对象；即使近期缓冲被全部淘汰，也额外保留这一条有界记录。`snapshot()["stats"]` 返回各区域的序列化大小（不是 Python 进程 RSS），供日志计量。Python 对象本身另有开销，因此不能把三个区域字节上限之和当作精确内存占用。

`read_evidence("E1")` 只能返回保留下来的短摘录（引用文本最多 400 字符）；它不承诺能恢复已丢弃的完整终端输出。不建立原始记录数据库、不默认写日志、不把不同任务的记忆混在一起。一个任务/一次独立尝试建立一个 `TaskContext`；不支持并发线程同时修改同一实例。

执行器捕获 stdout/stderr 的内存开销不在本组件控制范围内，宿主也应限长。输入输出可能包含密钥，调用方必须在上报前过滤敏感内容，避免把密钥放进命令、输出、目标或记忆；组件不宣称提供通用脱敏。

模型 token 预算可以用对应 tokenizer 计量：

```python
view = context.build_prompt(
    max_units=3000, reserved_units=200,
    counter=lambda text: len(tokenizer.encode(text)), unit_name="tokens",
)
```

`max_units` 是分给组件的数据块预算，不是整个模型窗口。若任务、约束和最新反馈仍放不下，抛出 `BudgetExceeded`，由宿主明确增加配额或事先降低 `Limits(feedback_chars=...)`；不会静默丢掉任务或最新结果。默认按 UTF-8 字节严格计量，不用字符数假装精确 token 数。

## 现有 BestFGS 数据类型适配

```python
from terminal_context.adapters import from_command_result

# result 为原项目 CommandResult；本包不导入或改写冻结版本。
feedback = context.observe(from_command_result(
    context.task_id, result, cwd=resolved_cwd,
    workspace=workspace_revision, environment=environment_revision,
))
```

适配器包含 stdin 的摘要用于区分输入，不保存 stdin；不同脚本通过 `python` 的 stdin 执行时，不会仅因命令名相同而合并成重复失败。宿主仍需过滤命令 argv 中的敏感内容。

## 本地验证

无需 API、网络、Docker 或云端权限。可不安装包，直接从本目录运行：

```powershell
$env:PYTHONPATH = "$PWD/src"
python -B -m unittest discover -s tests -v
python -B examples/replay.py
```

回放示例演示重复导入失败、环境改变后恢复、局部 pytest 通过；不会实际安装依赖或执行终端命令。测试覆盖配额、证据淘汰、范围失效、任务隔离、输入身份、压缩与验证边界。

局部 pytest 通过只记录为 `passed_scope_only`；无测试、截断、超时、未知退出码和缺少可识别摘要都不能得到通过结论。它不是 SWE/Terminal-Bench 官方评测器，也不决定 Agent 何时提交。

这些离线测试证明的是组件行为与约定一致，**不是对成功率或效率提升的实验验证**。现有项目发布目录、云端部署和正在进行的实验保持不变。
