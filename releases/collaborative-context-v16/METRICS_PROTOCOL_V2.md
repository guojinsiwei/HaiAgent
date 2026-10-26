# 指标协议 v2：重复不等于无用

> **v14 历史说明：** 本文描述旧指标协议，只用于解释历史产物。v14 不输出这些歧义别名，也不与旧轨迹混算；当前定义见 [V14_PROTOCOL.md](V14_PROTOCOL.md)。

日期：2026-09-21。实现目录 `metrics-protocol-v9`，基于独立冻结的 v8。本次只改报告与审计，不改算法、模型调用策略、成功标准和交互轮次。

## 保持不变的两项定义

1. **任务成功率**：固定题单上的官方 resolved/N。基础设施或评测未知时不冒充失败或零；保留原有未知计数及区间处理。内部成功/提交不替代官方评测。
2. **交互轮次**：`cli-comparison-v1` 原有的一次 CLI 执行反馈批次，不是模型请求数。空提案不算已执行交互；验证嵌套/最终复验沿用原规则。API 请求、Token 和耗时另报。

这是固定操作性定义，而不是说所有论文中的“轮次”天然指同一件事。

## 第三项拆分为自动代理与上下文审计

### A. 自动：机械重复调用率

`mechanical_repeat_rate = mechanical_repeat_calls / tool_calls`，整组报告采用各题分子之和除以各题分母之和（micro），不能和逐题平均（macro）混称。

一次调用被自动标为机械重复，当且仅当：之前存在规范命令签名、执行前工作区哈希和可用输出哈希相同的调用，且前后这两次调用各自均未改变工作区。命令签名含 argv、cwd、stdin 和超时；工作区不覆盖整个 OS/网络，输出包含返回码及超时/拦截状态，沿用原有限观测范围。

这套计算不变，改的是名称、解释与报告用途：它不是可避免重复的完整识别器。必要最终复验可能被计入；等价但不同写法、无关文件变化、时间戳输出都可能漏检。阶段分类不能解决这些语义问题。

报告同时给总体及各实际 phase：action、functional_verification、final_verification，以及日志出现的其他 phase。**不一律扣除验证调用，也不把某个 phase 自动标为必要/无用。** 旧日志没有阶段数据时返回 unknown/null，不补造阶段零值。

自动语法检查和运行时微经验文件检查原本不属于模型 CLI 调用，仍不混入这个分母。另看 Token、模型请求、总耗时，以及微经验前提检查次数/字节/耗时；这些内部操作不是免费成本，也不能用 CLI 数下降单独证明总体高效。

### B. 审计：可避免重复

自动报告的 `avoidable_repeat_rate` 先为 null，需要原始命令、输出、当前目标、相关状态变化和验证必要性等上下文证据。审计类别：

- `avoidable_repeat`：旧证据在当前条件下仍可用，重复询问同一问题，没有可说明的新增信息、进展或验证必要性；必须引用更早的调用及上下文。
- `necessary_reverification`：有具体理由的复核，不能仅凭“它是测试”判断。
- `other_nonredundant`：其他非冗余行为，包括有信息价值的失败。
- `uncertain`：不能确定；未填写另记 unreviewed。二者都不能悄悄当非冗余。

审计程序不调用 LLM、不执行建议命令、不代替审阅者判断。哈希日志只提供索引；没有完整上下文就应 uncertain，不凭重复标记贴标签。审阅身份、理由、证据引用只是可追溯记录，不构成自动事实证明。

## 固定抽样与分母

默认在**全部已完成调用**中无放回均匀抽取最多 30 条，固定 seed；不是只审计机械重复候选，否则无法发现漏检。原 trace SHA256、抽样策略、调用 ID 与规则一起冻结。删掉未审项、改样本或换日志都会拒绝。

设样本量 n，可避免重复 a，unknown/unreviewed 合计 u：

- 没有未知且 n>0，`avoidable_repeat_rate_in_sample = a/n`；否则点值 null。
- 始终可报告样本未知值范围 `[a/n, (a+u)/n]`。**这不是置信区间，也不反映抽样误差。**
- 只有审计覆盖整个 trace 且无未知，`whole_trace_avoidable_repeat_rate` 才给数值；部分样本不冒充全程比例。
- 零调用比例未定义；不完整日志不能进入审计，不能把缺失调用当零。

同一规则用于两种方法。包中不添加方法名，但查看原日志可能暴露身份，**不能声称完全盲审**。抽样结果仅作小规模诊断；正式比较应预先固定分层/抽样和复核方式。审计标为可避免也不是已完成反事实实验，`causal_tool_calls_saved` 仍为 null。

## 命令：历史日志可以离线复算

在本版本目录，使用实际解释器执行。所有输出必须是新文件，不覆盖源日志或历史报告。

```bash
# 只重新报告机械重复；无需 API Key、无需模型运行
python audit_tool_repetition.py report --trace /path/cli-metrics.jsonl --output mechanical-report-v2.json

# 生成固定、尚未贴标签的审计包
python audit_tool_repetition.py prepare --trace /path/cli-metrics.jsonl --output repetition-audit.json --sample-size 30 --seed 20260921

# 根据原始日志填写 items 的 label/reviewer/rationale/evidence_refs/earlier_call_ids
# 不要修改 protocol、样本身份或原始测量字段；再汇总
python audit_tool_repetition.py summarize --trace /path/cli-metrics.jsonl --audit repetition-audit.json --output repetition-audit-summary.json
```

若没有保存完整执行上下文，可以复算机械重复，但不能据此补出语义冗余审计结果。不保证旧数据足以完成全部新分析。

## 版本与兼容

低层轨迹版本继续是 `cli-comparison-v1`，报告协议为 `cli-metrics-report-v2`。新实验计划把报告协议写入冻结哈希。旧字段 `redundant_tool_calls`、`tool_call_redundancy_rate` 及汇总中的旧名称保留为兼容别名，**只能解释为机械重复**。新的独立 report 命令只输出清晰字段，不显示旧歧义字段。

`run_experience_ablation.py` 和 `compare_experiments.py` 都输出新字段、明确 unknown，并保留旧字段供旧消费者迁移。原“repeat_rate 降低 50% 达标”不再给布尔认证，返回无法根据机械重复判断。官方成功率和轮次比较逻辑保持原样。

本版不运行新实验、不自动审计旧研究结果、不新增外部 LLM 裁判。最终离线验证见 `VALIDATION_V9.json`。在新实验前冻结本协议；不能看到实验结果后再选择有利的分母或删掉必要复验。

最终全量回归：Windows / Python 3.12.14，471 项，464 通过、7 项平台/权限跳过，零失败；测试执行耗时 92.094 秒。原 v8 实现哈希和搜索、经验、裸模型、共享执行环境文件逐项复核未变。
