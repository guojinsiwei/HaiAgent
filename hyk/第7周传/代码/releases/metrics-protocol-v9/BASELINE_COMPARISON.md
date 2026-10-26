# DeepSeek Raw-CLI 与 BestFGS 的配对实验

**v9 指标更新：** 本文保留旧实验设置的历史说明；当前第三项按 [METRICS_PROTOCOL_V2.md](METRICS_PROTOCOL_V2.md) 执行。自动统计名称为“机械重复调用率”，不等同于可避免重复；旧“冗余降低 50%”不再由机械重复率自动判定达标。成功率与 CLI 反馈轮次定义不变。新实验使用新目录和协议哈希，不能把本文历史版本参数当成当前运行状态。

2026-09-18 准备修复后，两组均使用 `BestFGS-compare-v2` 新版运行器，不能混用旧版的工作区导入路径逻辑。固定题单不变，失败环境的构建版本调整与审计说明见 `PREPARATION_REPAIR.md`；其余已准备成功的环境保持不变。

## 1. 对照方法是什么

`src/bestfgs/raw_baseline.py` 是 **Raw-CLI baseline**，不是另一个搜索 Agent。

唯一主循环：把题目与完整历史发给同一个 DeepSeek → 执行它给出的命令 → 把原始反馈接到历史末尾 → 下一轮；提交最后工作区。

不使用搜索图、band、Score、压力调度、语义覆盖、结构化状态压缩、经验检索、规则提炼、技能、分支回退、候选排序、跨任务记忆、LLM 成功判断。不会因为失败而自动重跑一道题挑最好解。

保留的只有两组共有的基础设施：API 客户端与网络容错、JSON 命令格式校验、CLI 执行与安全限制、超时与输出截断、工作区复制、Python 语法/冲突标记门槛、补丁导出、外部官方评测。可选 `verification_commands` 是同一个环境接口，不是额外验证策略；裸模型不获得自动最终复验或成功判定。

原始历史不是“经验记忆增强”；CLI 模型必须看到自己之前执行的命令及反馈。这里不做任何摘要、检索或历史裁剪。历史太长导致 API 拒绝时保留故障，不暗中给 baseline 加压缩。它不是单次问答的 zero-shot patch baseline，也不是 mini-SWE-agent/ReAct 的完整复现；论文应使用准确名称。

## 2. 公平控制了哪些条件

| 条件 | 实现 |
|---|---|
| 题目 | 固定 `examples/swe100-plan.json`，同序、同 100 个 ID、同 base commit；沿用既有冻结测试集排除检查，不重抽、不丢掉难题 |
| 准备环境 | 共用已有 `ready.json` 的种子及 task Python；两个方法各自创建快照，不互读对方结果；运行前后核验种子内容和 `pip freeze` |
| 模型/API | 同一 `OpenAICompatibleJSONClient`、API Key 环境变量、明确的模型名/base URL、temperature/top-p、stream/JSON、重试和超时设置 |
| 思考设置 | 对照入口固定两组所有阶段为相同 reasoning effort（默认 high）；旧 Agent 的 high/max 混用不直接拿来作这一版配对实验 |
| 预算 | 同 24 个主动作批次、80 次 CLI 调用、每批最多 4 条、每题墙钟 14400 秒；关闭任务自适应加预算，倍数为 1；终验计入 Agent 的 80 次 |
| 命令反馈 | 同一个执行器、同路径映射、同任务 Python、相同输出截断和确定性语法门槛；BestFGS 后续的摘要是被比较的方法本身，baseline 不使用它 |
| 成功判断 | 两组都导出 patch，用同一个 `evaluate_swe_batch.py` 调用官方 Docker harness；不向求解模型提供 reference patch、评测测试或评测失败反馈 |
| 测试脚本 | 记录官方 harness commit/version、Docker 版本、测试 timeout；对每题官方 `eval.sh` 只记录 SHA256，对照报告检查两组一致，不把脚本内容发给模型 |
| 运行顺序 | 默认每题顺序交替，先跑哪个方法由 ID 的 SHA256 奇偶确定，以减轻时间/服务端漂移偏差；`--method` 允许仅执行某一组 |
| 实验溯源 | `comparison-protocol.json` 锁住源码哈希、题单、参数与环境指纹；同输出目录配置不匹配就拒绝续跑 |

两组的 **任务题面和约束相同，方法提示词当然不同**；不能一边要求 baseline 没有搜索机制，一边要求它使用 Agent 的搜索提示词。

“测试脚本相同”指最终外部官方评测。模型在求解过程中自行选择/生成的公开测试可以不同，这是方法行为的一部分；不能为了让过程测试相同而泄漏官方测试。

同 CLI 预算不等于同 LLM 预算。BestFGS 有规划、转移评估等额外调用，所以额外报告 `model_calls`、`api_requests`、prompt/completion tokens、运行时间和计数开销。当前实验回答“相同工具预算下哪个系统更有效”，不直接证明“相同 token/费用下更好”。无额外 key 校验模型请求，避免隐藏预检调用。

环境的工作区复制不是完整安全沙箱。现有 Notebook 环境仍依赖任务约束禁止修改外部环境；前后指纹检查能发现部分变化，但不能证明所有系统状态完全一致。不要让两组同时修改同一任务环境。

## 3. 三个指标的审计与统一定义

新字段统一放在 `comparison_metrics`，版本 `cli-comparison-v1`；旧字段保留作内部诊断，严禁混算。

| 指标 | 原有项目的问题 | 对照实验定义 |
|---|---|---|
| 任务成功率 | `succeeded` / `verified_success` 是内部判断，并非 SWE-bench resolved；裸模型没有内部成功分类器 | 官方 resolved 数 / 固定题数 N。空补丁为未解决；基础设施/评测错误为未知，报告上下界，未齐全不下达标结论 |
| 平均交互轮次 | 旧 `interaction_rounds` 是完成的搜索转移数，可能遗漏已执行但评估失败的动作，也不含最终复验 | `R_i` = 实际发出至少一条 CLI 请求的执行—反馈批次数。动作内普通命令和功能验证算一批；独立最终复验另算一批；空批次不算。均值为 ΣR_i/n |
| 工具调用冗余率 | 旧统计按 `(semantic_direction_id, command)` 和是否新覆盖来判断；依赖 Agent 专属状态，且没有纳入功能验证和终验 | **状态条件重复调用率（冗余代理）**：相同命令签名、相同执行前可观测文件状态、相同返回码/可见输出，并且执行后文件状态不变；此前已有一次这样的调用，则本次计入重复 |

### 冗余代理的细节

- 命令签名：argv、cwd、stdin、有效 timeout；不看描述文本/语义方向/分数，工作区绝对路径统一成占位符。
- 状态：文件内容、文件模式、符号链接目标；排除 `.git`、`__pycache__`、pytest/mypy/ruff 缓存及 `.coverage*`。不比较 mtime，也不观察网络、后台进程等工作区外状态。
- 输出：执行器实际保留的截断输出、返回码、blocked/timed_out 标志；不是未截断输出的完整语义。
- 第一次不算重复，之后满足条件的每次才算。代码改变后的同一测试通常不算重复。
- `T_i` 包括普通命令、功能验证、最终复验、被阻止的调用和超时请求；每个 `CommandSpec` 算一次，不拆开 `python -c` 内部的子操作。确定性内部语法门槛不算模型工具调用。
- 主汇总：`ρ = Σ redundant_i / Σ T_i`（micro）；同时报告逐题比率均值（macro）、调用数、重复数、分母和各阶段结果。
- `T_i=0` 时逐题比率为 `null`，不是 0；存在未完成工具请求时也不伪造比率。
- `cli-metrics.jsonl` 在执行前记录调用，在执行后记录结果；异常不会把已发出的调用从分母抹掉。哈希记录器只观察，不参与动作选择。

**这不是语义上的“所有无用调用率”。** 必要复验可能重复；换个写法的无效命令可能漏检；外部状态改变可能无法观察。论文中必须标为“状态条件重复率/冗余代理指标”，不能仅凭它声称减少了全部无效操作。若想研究语义冗余，需要另做盲审标注及一致性验证，不宜临时加一个 LLM judge。

### 平均轮次的统计群体

同时输出两组 **相同题目** 的：

1. 全部结果完整、单次尝试配对题的轮次与重复率（包含解不出的题，展示总体预算消耗）。
2. 两组都被官方判定解决的交集，比较“完成相同工作”的轮次与重复率。

第二组用于效率目标检查，但属于条件性分析，会有成功样本选择偏差，必须和第一组、成功率、题目 ID/n 一起报告。不能各取自己成功的题求平均，也不能把“提前失败、调用少”宣传为效率提升。

`compare_experiments.py` 输出固定种子的 2000 次题目级配对 bootstrap 区间、成功率 McNemar 精确检验、排除 ID。题目级区间未建模仓库内相关性，也不能替代多随机重复实验；一轮 100 题不保证有足够统计功效，更不能代表 Terminal-Bench 2 的结果。

### 图片中的目标怎么读

- “成功率提高 10%”有歧义：相对增长 `(p_A-p_B)/p_B`，与提高 10 个百分点 `p_A-p_B ≥ 0.10` 不同。报告两者；论文主口径应在看结果前约定。
- “平均轮次降低 30%”：`1 - mean(R_A)/mean(R_B) ≥ 0.30`。
- “冗余率降低 50%”：`1 - ρ_A/ρ_B ≥ 0.50`，不是减少 50 个百分点。baseline 为 0 时相对降低无定义。
- 分开显示点估计达标与置信区间下界达标；它们不等价。三项同时宣称还需要考虑多重比较，当前报告不自动给“科学结论通过”的认证。

### 故障与重试

网络/认证/未知 API 故障立即保留证据、停止批次；显式 `--retry-infrastructure` 才允许新尝试。已经正常结束但解错的题不会自动重试。合法 API 返回后模型仍持续输出无效 JSON/结构，记录为模型输出失败，不冒充网络故障排除。

所有先前尝试保存在 `previous_attempts`。发生重试的题不混入单次尝试效率结论，报告明确标记协议不完整；要做严格 pass@1 的主实验，最好在环境/网络稳定后做新的完整配对重复，而不是挑选多次最好结果。

## 4. 如何运行（先预检，暂不付费）

不要覆盖云端旧项目。本版本上传/解压到**新目录** `/mnt/lizh639/BestFGS-compare-v2`；继续复用 `/mnt/lizh639/bestfgs-runs/swe100-v1` 已准备的环境。先完成 `PREPARATION_REPAIR.md` 中剩余 15 题的修复，确认 100 题全部准备成功，再启动下面的配对实验。

进入新项目目录，使用现有 agent Python：

```bash
/mnt/lizh639/envs/bestfgs/bin/python run_comparison.py plan \
  --prepared-root /mnt/lizh639/bestfgs-runs/swe100-v1 \
  --output-root /mnt/lizh639/bestfgs-runs/swe100-compare-v1
```

`plan` 不调用模型、不写结果目录，列出 ready/missing。必须同一批 100 题全部就绪才允许 `run`，不会偷偷改成 73 题。预检就绪不保证外部 API 当前一定可用。

确认参数、余额和题目全部就绪后，在已设置 `DEEPSEEK_API_KEY` 的 tmux 会话中执行（**会付费、默认跑两组共 200 个 task attempts**）：

```bash
/mnt/lizh639/envs/bestfgs/bin/python run_comparison.py run \
  --prepared-root /mnt/lizh639/bestfgs-runs/swe100-v1 \
  --output-root /mnt/lizh639/bestfgs-runs/swe100-compare-v1
```

仅跑裸模型追加 `--method raw`，仅跑 Agent 追加 `--method bestfgs`；优先使用默认配对交替顺序。重复相同命令会跳过完成题；故障需先检查，再显式授权重试。所有恢复命令必须保持原配置。

每组自动生成：`summary.json`、`predictions.jsonl`、`evaluation-bundle.zip`；逐题有执行轨迹、日志、补丁。原 `swe100-v1` 的结果和准备文件不被修改。

下载两份 bundle 到本机（PowerShell）：

```powershell
scp cubestudio_container:/mnt/lizh639/bestfgs-runs/swe100-compare-v1/bestfgs/evaluation-bundle.zip "$env:USERPROFILE\Downloads\bestfgs-comparison.zip"
scp cubestudio_container:/mnt/lizh639/bestfgs-runs/swe100-compare-v1/raw/evaluation-bundle.zip "$env:USERPROFILE\Downloads\raw-comparison.zip"
```

在本机项目目录，用已配置的 Python 分别调用**同一官方评测入口**（需要 Docker Desktop/WSL；无需 sb-cli 云 API）：

```powershell
python evaluate_swe_batch.py --bundle "$env:USERPROFILE\Downloads\bestfgs-comparison.zip" --output-root benchmark_results/paired-official
python evaluate_swe_batch.py --bundle "$env:USERPROFILE\Downloads\raw-comparison.zip" --output-root benchmark_results/paired-official
```

复制两次输出的 `results.json` 真实路径后：

```text
python compare_experiments.py --agent <Agent的results.json> --baseline <raw的results.json> --output benchmark_results/paired-comparison.json
```

不要把 `agent_succeeded=false` 当作裸模型失败：baseline 故意没有内部成功分类器，patch 仍正常交给官方测试。

## 5. 与旧结果的关系

旧 Agent 的轮次和冗余率不能直接和这里的新定义比较，也无法仅凭旧 summary 完整追补。它们仍可用于内部排查；正式三指标对照需两组都启用新版计数器。

这个 baseline 能检验完整 BestFGS 系统相对简单 CLI 模型的收益，不能单独证明收益来自“图”“记忆”或“压力”。分别证明机制贡献需要预注册消融，不应该把全部收益都归于某一个模块。本次没有增加那些消融，也没有启动付费实验。

2026-09-18 离线验证：共 276 项 unittest，Windows Python 3.12 跳过 4 项，其余通过；WSL/Linux Python 3.14 跳过 1 项，其余通过。新增 32 项测试覆盖基线真实命令执行、原始历史、预算、故障分类、重复率、双组导出/续跑、官方测试脚本不一致拒绝等。模型由假客户端/本地 HTTP 测试服务器替代；尚未在云端 Python 3.11 上进行真实付费 100 题对照，不能据此声称性能达标。

参考：官方 [SWE-bench evaluation harness](https://www.swebench.com/SWE-bench/guides/evaluation/) 定义外部评测工作流；[Deep RL at the Edge of the Statistical Precipice](https://arxiv.org/abs/2108.13264) 说明仅凭点估计和少量实验汇报改进的统计风险。这里的 CLI 重复率是本项目明确声明的操作性定义，不宣称是该论文或 SWE-bench 的官方指标。
