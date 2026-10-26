# Meta-Agent 与跨任务候选接纳 API

实现位置：`src/recuris/evolution.py`。本模块不执行终端命令、不运行评测、不修改 memory 文件。所有测试使用预制模型回复和虚构评分；没有实验结果。

## 与论文的对应关系

- 论文 §2.3.1–2.3.4（PDF pp8–9）：先从结构化轨迹归因至 E/W/rho/C，再逐组件提出修改，未归因组件保持不变。外部评测 gate 决定是否部署候选。
- 论文 §2.3.5、§3.5（pp10、23–24）：TTA 限于同一任务、只允许 E 更新。Meta-Agent 只能收到任务指令、失败轨迹及一个官方失败 bit。TTA 不使用跨任务 dev gate。
- 本实现使用固定的两阶段 JSON 协议与数据型 memory patch，不允许模型重写 Python 代码、checker kernel、基础模型或 Meta-Agent。它是论文方法的 LongCLI 移植，不是作者 Claude Code Meta-Agent 源码的逐字复制。
- 本模块的 `strict_no_regression_v1_engineering_choice` gate 是**工程选择**。它比作者当前 `metaagent/gate.py` 的默认 gate 更严格：作者默认条件包括净增大于 0、regression cap 为 1、源任务通过率提高，置信区间用于 `significant` 标记；本文实现采用逐 anchor 不退步、dev 均值不下降以及全部源 attempt 通过。不能将这里的阈值称为论文唯一或原始阈值。作者实现参见 [Recuris 仓库](https://github.com/Gen-Verse/Recuris)。

## 提议候选

```python
from dataclasses import asdict
from recuris.client import ModelConfig, OpenAIChatClient
from recuris.evolution import MetaAgent
from recuris.memory import load_memory

client = OpenAIChatClient(ModelConfig(model_name="YOUR_PROVIDER_MODEL", temperature=0))
meta = MetaAgent(client, max_context_chars=120000,
                 max_parse_attempts=2, max_total_seconds=600,
                 max_model_calls=16)

# 仅当外部评测驱动确认该 attempt 已被官方 verifier 判为失败时调用。
candidate = meta.propose(load_memory(), instruction, actor_trace, mode="tta")
candidate_record = asdict(candidate)
```

`mode` 只能为 `tta` 或 `cross_task`。`propose` 接口没有可装入 verifier/test/reference 的 feedback 参数；发送给 Meta 的结果字段由程序固定为 `official_success: false`。驱动负责确认这一 bit 的真实性，以及建立任务、attempt 和轨迹的对应关系；该函数不能仅凭一个 JSON 判断轨迹来自哪次真实评测。

`client.complete(messages, *, purpose, deadline_monotonic)` 必须返回 `ModelReply`。每次 `propose` 独立计算调用与时限预算，包括解析重试；模型传输自身的 HTTP 重试由 client 管理。字符预算不等于 tokenizer 的 token 预算。

`actor_trace` 是结构化步骤数组，例如：

```json
[
  {
    "step_id": 1,
    "state_before": [],
    "invoked_skills": [],
    "action": {"command": "cat /workspace/service.conf"},
    "observation": {"output": "Required setting is absent", "completed": true, "exit_code": 0},
    "proposed_state": {},
    "checker_decisions": [],
    "state_after": [],
    "event": "turn"
  }
]
```

这个例子只演示 Meta 输入形状，不是可执行 benchmark attempt。完整轨迹应直接使用本包 runtime 输出。允许字段严格限于上例的十个字段，`step_id` 必须存在且唯一；它可为非负整数或非空字符串，整数 `1` 与字符串 `"1"` 不等同。输入中的额外 task/result 包装对象会被拒绝；嵌套的 `verifier`、`verifier_output`、`tests`、`test_results`、`expected_output`、`reference_solution`、`reward`、`score`、`official_success` 等字段也被拒绝。

此限制不能识别调用者故意塞进普通 observation 字符串的答案；调用方必须始终从 actor-visible log 构造输入。公开终端输出、用户允许的自测命令仍然可以作为真实轨迹证据。

超出上下文预算时，仅移除最旧的完整步骤，并记录 `omitted_step_ids`。不截断单条 JSON 或 observation；memory、instruction 与至少一条完整步骤仍不能放入预算则报错。诊断只允许引用实际传给 Meta 的步骤。

定位阶段回复：

```json
{
  "diagnoses": [
    {"component": "E", "description": "Configuration changes were not read back.", "evidence_step_ids": [1]}
  ],
  "noop_reason": ""
}
```

每个诊断必须引用至少一个已提供步骤，不能编造 step ID。多个诊断可以归因同一组件。TTA 中所有诊断必须属于 E；cross-task 可以归因四个组件。

随后，程序对每个归因组件单独调用 patch 阶段：

```json
{
  "component": "E",
  "replacement": [
    {
      "id": "read_back_config",
      "description": "Verify edited configuration before completion.",
      "content": "Read back every requested setting and validate the resulting behavior.",
      "tags": ["configuration", "verification"]
    }
  ]
}
```

`replacement` 是该组件的完整替代值，经过 `validate_memory` 校验。归因组件集合必须与真正发生变化的组件集合完全一致；未归因组件从原 memory 深拷贝。不能通过提供文件路径、脚本、额外 schema 字段或 patch 另一个组件扩大修改范围。

三种结果：

1. 成功候选：返回 `Candidate`，包含 `diagnoses`、`base_digest`、`candidate_digest`、`candidate_memory`、`changed_components`、`mode`、token/call 用量、耗时、可见/省略步骤 ID。产生候选**不表示跨任务 gate 已批准**。
2. 无需修改：定位回复 `{"diagnoses": [], "noop_reason": "具体原因"}`；返回 `no_op=true`，原/候选 digest 相同，不调用 patch 阶段。
3. 输入错误抛出 `ValueError`；模型传输失败、解析次数/调用/时间/上下文耗尽抛出 `EvolutionError`，携带 `model_calls`、`input_tokens`、`output_tokens`。任何失败都不产生部分部署。

## 纯函数 gate

```python
from recuris.evolution import evaluate_gate, pair_scores

source = [{"task_id": "evolve-a", "seed": 0, "baseline": False, "candidate": True}]
dev = [
    {"task_id": "dev-anchor", "seed": 0, "baseline": True, "candidate": True},
    {"task_id": "dev-other", "seed": 0, "baseline": False, "candidate": False},
]
report = evaluate_gate(source, dev, test_task_ids=["test-unseen"])
# 这是 API 示例数据，不是真实运行结果。仅在 report.accepted 时才能部署。
```

`source` 和 `dev` 必须非空。每行严格为 `{task_id, seed, baseline, candidate}`，`seed` 是非负整数，评分只能是准确的布尔值。`null`、`0/1`、字符串、缺失结果、执行异常都不能被转成失败。相同 task/seed 不可重复；source/dev/test 按 task ID 互斥，即使 seed 不同也不能交叉。

如果基线与候选分开输出，可以先调用：

```python
paired = pair_scores(
    [{"task_id": "evolve-a", "seed": 0, "success": False}],
    [{"task_id": "evolve-a", "seed": 0, "success": True}],
)
```

`pair_scores` 要求两侧 `(task_id, seed)` 集合完全相等，拒绝静默丢弃缺失行。调用方仍须与预先固定的 split/task/seed manifest 核对，避免两侧同时遗漏同一任务后形成表面完整的配对数据。test 成绩不属于任何允许的 gate 输入字段。

接纳必须同时满足：

- 每个 source task 至少有一个原失败 attempt 变为通过，且全部 candidate source attempt 通过。
- dev 包含至少一个原先通过的 anchor；每个原先通过的 task/seed 配对都继续通过。
- dev 平均通过率不下降。

返回 `GateReport` 包含 `accepted`、拒绝原因、源修复数量、anchor 数量及退步数量、dev 两侧均值与策略标识。合法但未达标的证据返回 `accepted=false`；字段缺失、分割重叠等无效证据抛出 `ValueError`。函数不接触模型、不读文件、不执行评测、不接受测试集评分，也不自动写回 memory。

## 从官方 attempt 接纳候选

交付的 CLI 使用 `admission.py`，而不是直接信任调用方手填的布尔分数。先通过 `recuris tta --mode frozen --attempts 1` 保存原记忆上的官方失败，再执行 `recuris propose --mode cross_task`。候选目录保存完整 `candidate.json` 和可评测的 `memory.json`；候选正文按原值持久化，以保持 `candidate_digest` 可核验。

评测前冻结 `split.json`，例如：

```json
{
  "evolve": ["EVOLVE_TASK"],
  "dev": ["DEV_ANCHOR_TASK", "DEV_OTHER_TASK"],
  "test": ["UNSEEN_TEST_TASK"],
  "seeds": [0, 1]
}
```

这里的任务名是占位符，必须替换成数据集的真实目录 ID。`seeds` 是重复采样编号，不是传给模型的确定性随机种子。evolve/dev 必须非空，三个任务集合互斥。dev 应包含至少一个原记忆通过的 anchor。

接手者针对候选来源任务及全部 dev 任务、每个编号，分别用原记忆与候选记忆运行一次 `recuris tta --mode frozen --attempts 1`。统一固定 Actor 模型、参数、端点、代码、预算和任务文件。每个评测引用各自新目录内的 `attempt-01`；不能把 campaign 目录或普通 `tb run` 的结果目录直接当成 sealed attempt。

`evaluations.json` 形状如下；完整文件必须含源任务及每个 dev 任务与全部 `seeds` 的笛卡尔积，例子仅展示单行：

```json
{
  "base_digest": "COPY_FROM_candidate.json_base_digest",
  "candidate_digest": "COPY_FROM_candidate.json_candidate_digest",
  "source": [
    {
      "task_id": "EVOLVE_TASK", "seed": 0,
      "baseline_attempt_dir": "runs/source-base-0/attempt-01",
      "candidate_attempt_dir": "runs/source-candidate-0/attempt-01"
    }
  ],
  "dev": [
    {
      "task_id": "DEV_ANCHOR_TASK", "seed": 0,
      "baseline_attempt_dir": "runs/anchor-base-0/attempt-01",
      "candidate_attempt_dir": "runs/anchor-candidate-0/attempt-01"
    }
  ]
}
```

这些相对路径以 `evaluations.json` 所在目录为基准。`candidate.json` 中的 `source_attempt_dir` 则以候选文件目录为基准；CLI 自动保存绝对路径。

```bash
python -m recuris admit \
  --base-memory /path/to/base-memory.json \
  --candidate /path/to/proposal/candidate.json \
  --evaluations /path/to/evaluations.json \
  --split /path/to/split.json --output-dir /path/to/new-admission
```

`admit` 全程离线。它校验源失败、候选归因/摘要、官方结果与日志哈希、任务和模型来源、完整配对及独立 run/trial 身份。无效证据会报错且不创建输出目录；合法 gate 接纳或拒绝均保存 `gate.json` 和下一轮的 `memory.json`。拒绝时逐字节保留原记忆。命令退出码 0 仅表示完成 gate，应读取 `gate.json.accepted` 判断是否接纳。

不能用 test 集运行结果填写 `source` 或 `dev`。未调用模型生成候选、未做外部评测时，不能制作声称通过的 gate 记录。
