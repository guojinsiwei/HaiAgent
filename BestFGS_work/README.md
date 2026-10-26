# BestFGS

BestFGS 是从 `plore_ploit` 独立复制后改造的新项目。原项目不受影响。默认 Agent 已从在线 MCTS/UCB 调度切换为**阶段自适应语义最佳优先图搜索**（Phase-Adaptive Semantic Best-First Graph Search）。

## 核心机制

1. 模型先生成语义地图和一个 Bootstrap 动作。语义方向只是任务空间的先验划分，不表示已经探索。
2. 搜索维护全局 `(状态, 动作)` 前沿，每轮在所有可达状态中取优先级最高的一项，不按 UCB 访问次数走树。
3. 超预算、已执行、已覆盖、失效规则、命中 avoid 等动作先被硬过滤，再进入优先队列。
4. 求解压力 `p∈[0,1]` 随语义覆盖率、已用交互轮次和已用工具预算单调上升。24 轮基础预算下，即使覆盖不足也会在第 7 轮前后完全转入求解侧。
5. 同一套优先级连续变权，不做 Beam→Best-First 的硬切换，也不在切换时删除旧分支。

优先级主分量如下：

| 分量 | 前期权重 | 后期权重 | 依据 |
| --- | ---: | ---: | --- |
| 真实进展 | 0.20 | 0.35 | 命令、修改、验证等真实反馈 |
| recommend | 0.10 | 0.25 | 当前任务、当前状态下仍有效的成功经验 |
| 语义新颖性 | 0.30 | 0.05 | 未探索方向优先 |
| 信息增益 | 0.30 | 0.10 | 是否指向未解决问题并声明可观察证据 |
| 候选成熟度 | 0.10 | 0.25 | 修改、验证及候选动作信息 |

最终分数还扣除工具成本、重复方向和失败历史，并加入最高 0.10 的等待老化奖励，防止低分方向永久饥饿。`recommend` 在前期只作为加权提示；求解压力达到 0.5 后才提升优先等级。方向失败会使其推荐置信度按 `1/(1+失败次数)` 衰减。

优先等级先于同等级分数：

- 3：有强真实进展或高成熟度候选；
- 2：有中等真实进展，或中后期的有效 recommend；
- 1：能带来新语义或信息；
- 0：兜底动作。

## 动作容量与图结构

每个状态的语义动作容量动态保持在 **3–6**：基础容量为 3，未覆盖方向、未解决问题、不完整计划和可召回的推荐方向会增加需求，硬上限为 6。容量不读取访问次数，因此不是 progressive widening，也不会僵硬地固定为 2。

前期每个语义方向在待选前沿最多保留 1 个动作，求解阶段最多保留 2 个替代动作。这只控制候选多样性，不像 Beam Search 那样要求同层动作全部执行。语义等价且工作区指纹相同的状态可保守合并；旧分支始终保留，可在主路线失败后重新被全局队列选中。

## 成功、预算与记忆边界

- 默认基础预算为 24 轮 / 80 次工具调用；题面判定为难题时为 33 / 108。默认 `budget_multiplier=1`，不会自动扩成数倍预算。
- 工具预算的 10%、最多 8 次保留给最终复验。
- 模型的 `task_success` 只作诊断；真实修改和功能测试通过后仅形成 `candidate_success`。默认还要通过独立证据审计 API 才形成 `verified_success`，随后立即停止并在交付前复验。
- 长程记忆严格限于**同一道任务**的跨轮次和跨分支。每次 `TaskRunner.run()` 都新建规则库、知识板和搜索图，不把上一题经验送入下一题。
- 初始语义地图冻结为“核心方向”，核心覆盖率用于阶段切换和在线奖励；运行中新发现方向只影响动态发现覆盖率，因此不会因为分母临时扩张而产生虚假负奖励。文件修改导致旧证据失效时，核心覆盖仍允许真实下降。
- 有效探索比例、知识复用率和工具冗余率继续作为事后指标，不参与在线分数。

## 独立成功审计 API

真实入口默认使用 `--success-judge-mode required`，每题最多 2 个格式有效的审计结果；同一候选的格式错误最多修正一次，包含修正在内最多 4 次客户端调用（底层网络重试另受模型配置限制）。审计器看不到求解模型的成功声明，读取任务、从初始快照到最终候选的累计补丁、实际文件清单和新鲜测试输出。每项补丁风险都必须有功能测试证据。有效的 `fail` 或 `insufficient_evidence` 在剩余审计额度内转成具体验证缺口；审计不可用或额度耗尽时保存候选、未验证收尾，不继续消耗求解轮次。补充验证不要求再次修改已有候选。功能测试在一次性副本执行，测试产物不进入交付目录。

官方评测结束后，成功/失败任务平均交互轮次按官方标签计算，内部口径保存在 `agent_diagnostic`。旧实验可用 `refresh_experiment_reports.py` 离线生成校正摘要；详见 [本次改动说明](CHANGES_20260914.md)。

未单独配置时，审计器沿用求解服务商、模型和 API Key，但使用独立上下文和零温度。当前正式实验推荐使用阿里云百炼北京地域的固定快照，与 DeepSeek 求解器保持服务商独立：

```powershell
$env:SUCCESS_JUDGE_PROVIDER = "dashscope"
$env:SUCCESS_JUDGE_MODEL = "qwen3.7-plus-2026-05-26"
$env:SUCCESS_JUDGE_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:SUCCESS_JUDGE_API_KEY = "你的百炼API-Key"
```

`dashscope` Provider 不发送 OpenAI 的 `prompt_cache_key` 或 DeepSeek 的 `thinking` 对象，而是把本项目的 `low/high/max` 映射为千问的 `enable_thinking` 开关。固定模型快照用于防止对照实验期间 Judge 静默升级；如使用业务空间专属域名，只需覆盖 `SUCCESS_JUDGE_API_BASE`。

也可通过测试脚本的 `--success-judge-provider`、`--success-judge-model`、`--success-judge-base-url` 和 `--success-judge-api-key-env` 覆盖。Judge 调用不计作环境交互轮次，但会单独输出调用数、token 和缓存统计。

旧 `mcts.py` 被保留为快照执行、预算、RE-TRAC、规则整理和最终复验的公共实现，以及消融基线；默认 `TaskRunner` 实例化的是 `SemanticBestFirstGraphSearch`，其在线选择不执行 UCB、rollout 或奖励回传。

## 结果可审计性

命令行 JSON、检查点和 SWE `agent-results-*.json` 会记录：

- `search_algorithm = phase_adaptive_semantic_best_first`；
- 每轮全局前沿大小、求解压力；
- 优先等级、总分及每个分量/惩罚项；
- 交互轮次、工具调用、预算、停止原因、模型用量和事后研究指标。
- 模型成功声明次数、候选成功次数、独立审计判定与审计 API 用量；
- 独立审计对每个确定性补丁风险的处置与所引用证据；
- 固定核心覆盖率和动态发现覆盖率的分子、分母及变化原因。

## 离线验证（不调用 API）

```powershell
cd C:\Users\54177\Desktop\BestFGS
$env:PYTHONPATH = "$PWD\src"
python -B -m unittest discover -s tests -v
```

`tests/test_best_first.py` 专门验证动态权重、单调求解压力、推荐失败衰减、全局前沿前后期选项变化、方向多样性、禁用 UCB 回传，以及验证成功后提前停止。完整测试还覆盖预算、任务间记忆隔离、冻结清单、RE-TRAC、规则、语义证据失效和评测汇总。

## 四个开发评测入口

- `run_terminal_bench_tenth.py`：Terminal-Bench 2 非冻结开发池随机抽 1/10；
- `run_terminal_bench_2random_tasks.py`：Terminal-Bench 2 非冻结开发池随机抽题，默认2题，可用 `--sample-size N` 修改；
- `run_swebench_tenth.py`：SWE-bench Verified 非冻结开发池随机抽 1/10；
- `run_swebench_2random_tasks.py`：SWE-bench Verified 非冻结开发池随机抽题，默认2题，可用 `--sample-size N` 修改。

四者都会在首次运行时保存带 SHA-256 的抽样清单，后续直接复用相同题目及顺序。原有固定两题、SWE 18题和冻结测试入口继续保留，但不属于这四个开发抽样入口。

具体 PowerShell 命令和清单复用规则见 [BENCHMARKS.md](BENCHMARKS.md)。去掉 `--dry-run` 会真实调用模型并消耗 API；本项目的离线测试通过不代表真实基准性能已经提高。
