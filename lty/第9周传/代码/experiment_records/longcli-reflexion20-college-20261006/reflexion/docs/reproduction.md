# Reflexion 论文机制与 LongCLI-Bench 迁移说明

本项目复现 Reflexion 的核心推理时机制，并将它接入 LongCLI-Bench 的终端任务接口：Actor 执行任务，Evaluator 判断本次尝试，Self-Reflection 将失败轨迹和评价转化为下一次可执行的改进建议，后续 Actor 读取有界反思记忆。三个角色使用独立提示和独立模型调用，默认调用同一个配置的模型，不更新模型权重。

交付范围是方法实现与适配器。没有运行真实模型请求、Docker 任务或 LongCLI-Bench 实验，不提供成功率或性能复现结论。本项目采用**终端状态延续的 Reflexion 迁移**；它不等同于论文 ALFWorld 环境重置后的重试，也不宣称复现论文各基准的数值结果。

## 论文依据

以用户提供的 NeurIPS 2023 会议版 PDF 为主要依据。下文页码指该 PDF 的页码，共 19 页；文档第 1 页与论文印刷页码一致。完整来源及本地文件 SHA-256 见 [paper-source.json](paper-source.json)。

- [NeurIPS 2023 论文页面](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html)
- [NeurIPS 2023 论文 PDF](https://proceedings.neurips.cc/paper_files/paper/2023/file/1b44b878bb782e6954cd888628510e90-Paper-Conference.pdf)
- [作者官方 Reflexion 仓库](https://github.com/noahshinn/reflexion)，论文中的旧地址 `noahshinn024/reflexion` 现对应此仓库。

| 论文内容 | 位置 | 本项目的对应机制 |
|---|---|---|
| Actor、Evaluator、Self-Reflection 三个功能角色 | 第 3–4 页，§3 | 独立 Actor、Evaluator、Self-Reflection 调用；允许共享同一个基础模型 |
| Actor 根据观察、当前轨迹与记忆选择动作 | 第 3–4 页，Actor / Memory | 当前 trial 保存动作和终端观察，Actor 同时接收该任务已有反思 |
| Evaluator 接受轨迹，生成任务相关评价；可使用规则或 LLM | 第 4 页，Evaluator | 默认 LLM 自评价，并使用重复命令等失败启发式 |
| Self-Reflection 根据稀疏奖励、当前轨迹及已有记忆生成具体反馈 | 第 4 页，Self-reflection | 失败后调用反思角色，提供原始任务、执行轨迹、评价反馈与已有反思 |
| 短期记忆是轨迹，长期记忆是反思文本 | 第 4–5 页，Memory | 新 trial 重建 Actor 对话，仅通过有界反思延续失败经验 |
| 长期记忆容量 Ω 通常为 1–3 条 | 第 5 页，Reflexion process | 默认容量 3，按先进先出保留最近反思；仅当前任务本次运行有效 |
| 同一动作和相同响应超过 3 次，或执行超过 30 个动作，可触发失败后反思 | 第 5 页，§4.1 | 默认连续 4 次相同非空命令及相同观察触发启发式失败；每 trial 步数上限默认 40，是迁移参数 |
| ALFWorld 失败后反思、记忆更新、环境重置，再尝试；保留最近 3 条反思 | 第 5 页，§4.1 | 保留反思和新 trial 机制；LongCLI 内部 trial 不重置容器，差异见下文 |
| HotpotQA 用答案精确匹配提供二值反馈，保留 3 条记忆 | 第 6 页，§4.2 | 不移植答案精确匹配 oracle，不读取隐藏答案或官方隐藏测试 |
| 编程设置使用最多 6 条自生成有效测试，记忆容量 1 | 第 7 页，§4.3 | LongCLI 采用终端 Agent 路径，不自动照搬函数级测试生成器；Actor 可运行任务允许的公开自测 |
| 不可靠的自评价可能产生错误停止或不必要修改 | 第 8 页，表 2–3 及分析 | 内部通过只是自评价结果；官方成败必须由 LongCLI harness 的测试结果判定 |
| 有限容量滑动记忆是论文实现的限制 | 第 9 页，§5 | 采用有界 FIFO，未加入向量检索、跨任务知识库或模型训练 |

## 运行语义

下列伪代码表达方法结构，实际实现还包括协议校验、上下文限额、全局预算、日志和错误处理。

```text
memory = []
for trial in range(max_trials):
    if global_budget_exhausted:
        stop
    trajectory = actor(task, memory, current_terminal_state)
    feedback = evaluator(task, trajectory)
    if feedback.passed:
        stop
    if no_next_trial or global_budget_exhausted:
        stop
    reflection = self_reflection(task, trajectory, feedback, memory)
    memory = (memory + [reflection])[-memory_size:]
    begin_new_actor_context()
    # LongCLI 迁移：终端文件、进程及 shell 状态继续保留
```

Actor 声称完成不直接代表任务成功。Evaluator 是另一次独立调用，结合可见的命令和输出检查是否有证据支持完成；终端循环等明显失败也可由启发式判定。失败反思需要指出观察到的具体问题、可能原因、下次可执行的修正与验证方式，不能只压缩环境描述，也不能声称看过未提供的隐藏测试。

反思产生后，下一 trial 使用新对话。旧 trial 的原始对话不会完整堆叠到下一次 Actor 提示中，失败经验通过反思文本保留。记忆属于同一次运行，不跨任务共享，也不会因为复用同一个 Agent 实例自动累积其他任务的经验。

仅失败且仍有下一 trial 时生成反思。最后一个 trial 失败后直接返回，不为不会被下一次 Actor 使用的记忆增加调用；成功后也不继续改写。默认最多 3 个 trial，因此通常最多生成 2 条反思，容量 3 在增加 trial 数量后才可能被填满。

## 论文伪代码与提示中的歧义处理

第 4 页 Algorithm 1 的循环条件印为 `not pass OR t < max trials`。按字面执行会在成功但预算尚未用尽时继续尝试，或者在失败且预算已经耗尽时继续循环。第 5 页正文说明循环直到 Evaluator 判断正确，实验又使用有限尝试次数。本项目据此实现**成功即停止，达到预算也停止**，等价于有预算时使用 `not passed AND trials_remaining`。这是对论文伪代码逻辑歧义的明确处理，不是逐字符照抄。

第 15 页附录 C.3 的 Self-reflection 指令与 Actor 的函数实现指令重复，不适合作为反思提示直接复制。官方 [Python generation 实现](https://github.com/noahshinn/reflexion/blob/main/programming_runs/generators/py_generate.py) 将反思定义为依据实现与测试反馈解释错误的短文本；官方 [ALFWorld reflection 实现](https://github.com/noahshinn/reflexion/blob/main/alfworld_runs/generate_reflections.py) 则要求分析过去策略并形成简洁的新行动计划。本项目采用正文与这些官方实现一致的角色划分，重新编写终端领域提示，没有复制论文全文或少样本轨迹。

## LongCLI-Bench 迁移的边界

### 1. 同一容器状态延续

论文 ALFWorld 会在失败后重置环境。LongCLI 适配器获得的是正在运行的终端 session，适配器内部没有通用环境快照和恢复协议。因此，新 trial 重置的是 Actor 对话，而文件修改、当前 shell 工作目录及运行中的进程继续存在。Actor 必须先确认当前状态再执行后续修复，不能假设回到了干净的初始仓库。

这项选择适合终端长任务的继续修复，但会改变论文中的试验条件。如果后续研究需要“失败后恢复相同初始环境”的严格实验，需要在 harness 层补充可验证的容器快照和重置支持；只清空模型对话不能实现该条件。

### 2. 自评价与官方评分分开

默认评价来自本次执行的可见证据与 LLM 自评价，没有外部隐藏测试 oracle。适配器不会调用官方隐藏测试评分流程来决定内部 trial 是否继续。LLM Evaluator 可能误判，Actor 自行运行的公开测试也可能不充分，因此内部 `passed` 不应作为 LongCLI 成功率。

LongCLI 的官方测试和最终指标仍由它自己的 harness 产生。`AgentResult` 正常返回或者 `FailureMode.NONE` 也不代表任务通过。若使用上游的测试反馈轮，必须在报告中单独注明，因为这增加了额外反馈，改变了实验设置。

### 3. 三类尝试次数不同

| 层级 | 含义 |
|---|---|
| 本适配器内部 trial | 一次 Agent 执行中的 Actor → Evaluator → Reflection 重试；同一容器状态继续存在 |
| LongCLI 测试反馈轮 | harness 运行官方测试后，可能再次调用 Agent，并在输入中提供测试反馈 |
| LongCLI 独立 attempt | harness 创建的独立基准尝试，用于基准本身的统计 |

这三个数不能混用。反思记忆仅限当前 Agent 运行；本适配器不自动把它传递到上游创建的下一测试反馈轮或独立 attempt。安装与命令行用法见项目 [README](../README.md)。

### 4. 默认预算是迁移配置

| 参数含义 | 默认值 | 说明 |
|---|---|---|
| 最大 trial 数 | 3 | 初始尝试也计入，不是额外重试 3 次 |
| 反思容量 | 3 条 | FIFO；只保留当前运行的近期反思 |
| 每个 trial 最大 Actor 步数 | 40 | 不是论文 ALFWorld 的 30 动作设置 |
| 全局工具调用上限 | 120 | 约束一次 Agent 运行的工具消耗 |
| 全局模型请求上限 | 256 | Actor、Evaluator 与 Reflection 共享总预算 |
| 全局时间上限 | 3600 秒 | 不代替 harness 的外部超时设置 |
| 连续重复动作阈值 | 4 | 相同非空命令且相同输出连续出现；空命令轮询豁免 |
| 模型输入上下文上限 | 120000 字符 | 是字符数保护，不是模型 tokenizer 的精确 token 计数 |

当 Actor 上下文超限时结束该 trial；提交给 Evaluator 和 Reflection 的长轨迹采用显式标识的首尾截断。这是长终端轨迹的工程适配，会丢失被省略部分的细节，不应被解释为无损记忆或论文原始设置。选择模型时仍需保证其真实上下文容量足够。

默认同一个模型分别承担三种角色，并不意味着三者的判断在统计上独立。模型、提示、预算、公开测试质量及终端状态延续都可能影响最终表现。将来报告实验时应记录这些配置以及 LongCLI 提交版本；本次仅交付实现和离线验证，不对表现作推断。

