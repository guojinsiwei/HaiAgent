# BestFGS Slim

`BestFGS_Slim` 是对原 `BestFGS` 的保守瘦身版。原项目不受影响；搜索行为、评测入口和结果字段尽量保持兼容，但在线路径只保留一套**阶段自适应语义最佳优先图搜索**。

## 运行逻辑

1. 模型先生成语义地图和一个 Bootstrap 动作。语义方向只是待验证的任务空间，不等于已经探索。
2. 每轮把所有可达状态的待执行动作放入全局前沿，按证据优先级选一个动作执行。
3. 前期侧重新语义方向和信息增益；随着覆盖率、轮次和工具预算消耗上升，连续转向真实进展、有效 `recommend` 和候选成熟度。
4. 每个状态的动作容量由未覆盖方向、未解决问题、不完整计划和适用推荐共同决定，范围固定在 **3–6**，不依赖访问次数。
5. 只有真实功能验证覆盖成功标准后才产生 `verified_success`。默认成功后立即停止，并在交付前独立复验。

优先级的主要分量如下：

| 分量 | 前期权重 | 后期权重 |
| --- | ---: | ---: |
| 真实进展 | 0.20 | 0.35 |
| 当前任务内 recommend | 0.10 | 0.25 |
| 语义新颖性 | 0.30 | 0.05 |
| 信息增益 | 0.30 | 0.10 |
| 候选成熟度 | 0.10 | 0.25 |

分数还会扣除工具成本、重复方向和失败历史，并加入小幅等待老化奖励，避免低分方向永久饥饿。

## 瘦身边界

本版删除了旧 UCB 选择、访问次数/累计价值、奖励回传、工作节点选择模式和只为这些内部状态服务的测试。以下部分继续保留，因为它们仍直接影响正确性或课题指标：

- 隔离工作区、状态图和保守节点合并；
- RE-TRAC 结构化上下文、语义知识板和任务内规则；
- 24/80 基础预算、复杂题 33/108 调度、最终验证预留；
- `verified_success`、检查点、GRPO 样本和四项研究指标；
- Terminal-Bench 2 与 SWE-bench Verified 的冻结抽样和运行入口。

`src/cli_retrac_mcts/mcts.py` 只剩一个很小的兼容层，供旧实验命令导入 `MCTSConfig`；实际实现位于：

- `search_core.py`：预算、执行、任务内记忆、检查点和最终验证；
- `best_first.py`：全局前沿与阶段自适应选择；
- `priority.py`：可单测的优先级公式；
- `semantic.py` / `rules.py`：语义状态和任务内经验。

包目录仍叫 `cli_retrac_mcts`，这是为了不破坏 Docker/WSL 评测器中的 `python -m cli_retrac_mcts`，不表示运行时仍使用 MCTS。

## 预算与记忆边界

- 默认基础预算为 24 轮 / 80 次工具调用；题面启发式判定为复杂题时为 33 / 108。
- 默认 `budget_multiplier=1`，不会自动扩成数倍预算；评测脚本也保持原来的受控预算。
- 工具预算的 10%、最多 8 次留给最终复验。
- 记忆严格限于同一道任务的跨轮次和跨分支。每次 `TaskRunner.run()` 都创建新的规则库、知识板和搜索图，不跨题迁移。
- 交互轮次等于真实环境转移次数；模型重试单独计入模型用量，不伪装成 Agent 交互。

## 离线回归

```powershell
cd C:\Users\54177\Desktop\BestFGS_Slim
$env:PYTHONPATH = "$PWD\src"
python -B -m unittest discover -s tests -p "test_*.py" -v
```

回归测试不会调用真实 API、Docker 或下载数据集。

## 评测入口

- `run_terminal_bench_tenth.py`：Terminal-Bench 2 非冻结开发池随机抽 1/10；
- `run_terminal_bench_2random_tasks.py`：Terminal-Bench 2 非冻结开发池随机抽题，默认 2 题，可用 `--sample-size N`；
- `run_swebench_tenth.py`：SWE-bench Verified 非冻结开发池随机抽 1/10；
- `run_swebench_2random_tasks.py`：SWE-bench Verified 非冻结开发池随机抽题，默认 2 题，可用 `--sample-size N`。

四个入口首次运行时保存带 SHA-256 的抽样清单，后续复用相同题目和顺序。固定两题、SWE 18 题和冻结测试入口也继续保留。具体命令见 [BENCHMARKS.md](BENCHMARKS.md)。去掉 `--dry-run` 会真实调用模型并产生 API 费用。
