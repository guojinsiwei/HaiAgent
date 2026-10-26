# v7 经验机制的小样本开发消融

> **v14 历史说明：** 本文保留旧实验设计供追溯，不是 v14 的活动协议。v14 使用 `raw / memory_only / search_only / bestfgs` 四臂设计及新指标版本，见 [V14_PROTOCOL.md](V14_PROTOCOL.md)。

v10 中本入口已接入新的自动工具调用冗余率；成功率、交互轮次及三臂开关不变。主指标和 unknown 覆盖率按 [TOOL_REDUNDANCY_V10.md](TOOL_REDUNDANCY_V10.md) 解释；下方历史参数不意味着已执行新实验。

本入口只验证经验利用设计，不启动或覆盖历史 100 题实验，也不自动调用官方评测。它不是新的裸模型 baseline。

三组均运行当前 BestFGS、显式提交协议、同一任务种子与任务解释器、同一公开模型/API 配置、同一固定预算、同一套 CLI 测量器。唯一实验开关是 `--experience-mode`：

- `off`：不检索、不评估经验；允许影子观察用于诊断。普通交互历史、任务事实/知识板仍保留，不能解释成“失忆模型”。
- `legacy`：当前共享实现中的旧式经验利用，不是重新运行冻结 v5/v6 二进制。
- `conditioned`：当前共享实现中的条件化经验利用。

每题各跑一次，共 `3 × N` 次方法运行，`1 ≤ N ≤ 10`。大清单会报错，不会偷偷抽题或启动 100 题。三臂使用互不覆盖的结果目录；没有自动重试、续跑或官方评测。

## 准备输入

使用 `run_notebook.py` 已支持的**准备完成清单**，不是 Hugging Face 原始数据集行或 `predictions.jsonl`。格式为 `schema_version: 1`、`benchmark`、非空 `tasks` 数组。每题需有 `id`、`goal`、`workspace`，可以有 `success_criteria`、`constraints`。SWE 题还需完整 40 位 `base_commit`，以及干净、已准备好的独立 Git 克隆；可有 `prepared_commit`。

任务解释器必须通过共同的 `--task-python` 指定，或由每题 `task_python` 指定。清单中的相对路径相对清单所在目录解析。三臂对同一题一定使用同一个解释器；BestFGS 自身使用 `--python`，需要 Python 3.11+。

请**事先**选择 1–10 道开发题并固定清单。继承原入口对仓库冻结测试清单的排除检查，不提供绕过参数；额外未登记的留出集仍需选题时主动排除。不要按任何一臂的运行结果换题。这里不查看参考补丁、隐藏测试或在线解答。

## 默认：只预览，不付费

以下用 Linux 示例，路径需换成自己已准备的开发清单和新输出目录：

```bash
python run_experience_ablation.py \
  --task-manifest /mnt/lizh639/dev-tasks.json \
  --output-root /mnt/lizh639/bestfgs-runs/experience-dev-01 \
  --python /mnt/lizh639/envs/bestfgs/bin/python \
  --task-python /mnt/lizh639/envs/swe-sympy39/bin/python \
  --model deepseek-flash
```

不加 `--execute` 就只打印计划，不创建结果目录、不读取 Key 内容到输出、不调用模型。`--dry-run` 可显式表达同样意思。预览内的分臂命令用于审计；其输入清单要到显式执行时才落盘，建议使用统一入口启动。

默认每题每臂上限为 24 次迭代、80 次工具调用、每动作 6 条命令，`budget-multiplier=1`，关闭自适应预算。可在计划阶段统一修改 `--max-iterations`、`--max-tool-calls`、`--max-commands-per-action`，不能为某一臂单独加预算。两种 reasoning effort 都统一由 `--reasoning-effort` 设置，默认 `high`；温度默认 0.2。

`--schedule-seed` 固定三臂的交错执行顺序：题目顺序不变，三臂轮转排序平衡先后顺序。**它不是模型随机种子**，也不会增加运行次数。若研究需要多次随机运行，必须另开目录、明确总预算；本脚本不自动扩增重复次数。

## 核对后显式执行

在同一个命令最后添加 `--execute`。API Key 仅通过运行终端的 `DEEPSEEK_API_KEY` 继承，不放进命令或计划。可以再添加：

```text
--expected-protocol-sha256 <预览中的 protocol_sha256>
```

这会拒绝预览后发生的协议变化。入口记录任务/种子、解释器及包元数据、算法与编排代码、公开 API/线程配置和协议哈希；每次方法运行前后核对种子、实现及解释器元数据。输出目录必须原本不存在，连已有空目录也不接管。执行失败不会抹掉已有结果或自动重试；若发现准备环境/实现漂移，剩余运行停止。可以对部分结果先做只读汇总，再人工判断原因。

这些指纹不是整个操作系统/容器的快照，不能冻结外部服务、模型后端权重或其他进程。实验期间不要更新包、改种子或共享运行环境。API 响应中的实际模型名会保留，发现变化时不要把差异直接归因于经验机制。

## 汇总与指标边界

```bash
python run_experience_ablation.py \
  --output-root /mnt/lizh639/bestfgs-runs/experience-dev-01 \
  --summarize
```

只读现有结果，无需 Key。正常结束后也会自动保存 `ablation-summary.json`。它读取每题 `agent-result.json` 的 `experience_report`、交付状态、模型用量，优先用原测量器重算 `snapshots/cli-metrics.jsonl`；原始结果与 trace 不一致会明确标记。`task_experiences` 等详细来源仍在原始 agent-result 中，不能把聚合报告当作完整轨迹。

本目录使用指标报告协议 v2，见 `METRICS_PROTOCOL_V2.md`；成功率和轮次定义不变，第三项明确区分机械重复与审计后的可避免重复：

1. **任务成功率**只能来自官方测试。这里没有运行/导入官方评测，故 `official_resolved`、成功率均为 `null`，`official_unknown=N`。`known_resolved_count=0` 只是“目前没有已知的官方成功”，不是“成功率为零”。`submitted` 和 `local_validation_passed` 单独记录，不能替代官方 resolved。
2. **平均交互轮次**沿用 `cli-comparison-v1`：一次 CLI 反馈批次，不是一次 LLM 请求，也不是一次宏动作提案。单独记录实际模型调用、API 请求、Token、时间和缺失用量。
3. **机械重复调用率**使用 `mechanical_repeat_rate`，仍按原轨迹 `sum(redundant_tool_calls) / sum(tool_calls)` 复算，另给分 phase 明细。旧字段仅为兼容别名；必要复验可能重复，不能据此判断无效调用或冗余下降 50% 达标。`avoidable_repeat_rate` 在上下文审计前为 null，审计入口为 `audit_tool_repetition.py`。

固定清单中的失败、未开始、损坏制品和未完成 trace 全部留在每臂 `planned_N` 中。不完整测量不补成 0，也不悄悄删掉失败题：全队列效率值为 `null`，仅在 `recorded_complete_trace_subtotal` 单列已有完整 trace 的小计。Token/API 小计同样带可用题数，保留失败运行的已记录成本。它们不是账单，未返回或中断的请求可能缺少 Token 数据，因此金额 `monetary_cost=null`。

经验拒绝候选数、降权/门控事件仅为诊断记录：**不能当作已节省的实际工具调用数，也不能当作误拦率**。`false_block_rate`、`causal_tool_calls_saved` 维持 `null`。小样本的一次运行只能帮助定位机制行为，不能据此声称达到原 100 题目标、统计显著或因果提升。

本入口不声称实现同一模型前缀的断点续跑或反事实干预。离线读取已保存 trace 只是原指标的确定性复算；若另做决策回放，应固定原输入/状态并标为离线审计，不能混入真实运行成本或代替配对实验。

## 离线回归

```bash
PYTHONPATH=src:tests python -m unittest test_experience_ablation -v
```

测试只使用临时种子、假解释器指纹和脚本化结果，不调用任何模型/API、不提交官方评测。
