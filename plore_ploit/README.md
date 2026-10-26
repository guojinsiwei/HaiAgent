# plore_ploit

融合 `Explore_priority` 的初期探索与 `Exploit_priority` 的任务经验复用、连续修复和候选解保留。原项目不修改；本项目使用独立目录与评测运行名称。

## 搜索怎么运行

| 环节 | 本项目的行为 |
| --- | --- |
| 起步 | 生成语义地图，只执行 1 个 Bootstrap 动作；地图中的方向不等于已创建的分支。 |
| 初期探索 | 获得真实反馈后，优先生成/执行新的同级动作；节点无法扩展时才按 UCB 进入已有分支。每次生成后接纳 1 个新动作。 |
| 限制树宽 | 基础容量 **3**；未覆盖方向、未解决问题、不完整计划和当前环境可召回的 recommend 方向构成“不同语义需求”，需求超过 3 时容量随之增加，硬上限 **6**。已执行与排队动作都占容量。 |
| 转入求解 | 沿用原版条件：共享语义覆盖率达到 0.48，或已用约前 1/4 的轮次预算（总预算至少 6 轮时）。24 轮预算最晚第 7 轮转入求解。 |
| 证据有效性 | 已验证事实和 covered 方向绑定真实文件依赖。相关文件改变后只失效受影响证据并重新开放对应方向；无法可靠定位依赖时保守地按整个工作区处理。 |
| 预算感知 | 每次动作规划都会收到剩余轮次、工具额度和紧迫度。工具预算的 10%（最多 8 次）留给最终复验，临近上限时只接纳一个聚焦候选或必要诊断。 |
| 推荐利用 | 优先检查当前工作分支，再按 UCB 次序检查已建图中的可达、未耗尽节点。有经过运行时校验的 recommend 动作就先执行，下一轮重新检查，不按固定失败次数切换。 |
| 没有现成推荐 | 若召回到相关 recommend 且有扩展容量，本轮最多进行 1 次推荐动作生成探测。规则存在不代表一定有可执行动作；模型无法给出有效推荐就进入探索，不反复空转请求。 |
| 回退探索 | 恢复“新动作扩展优先、已有边 UCB 其次”。有当前修改快照时从该快照探索替代修复/必要诊断；当前分支确实耗尽再回根节点。出现新的有效推荐后，下轮重新优先利用。 |
| 成功结束 | 保留 `verified_success` 与最终复验，默认一旦经验证成功就结束。只有模型声称成功不够。 |

“前 1/4”和“0.48”是继承的可调试启发式，不是成功率保证。语义树宽是每节点容量，不是整张图的节点数，也不要求先把容量跑满。切换求解阶段会清空旧待选队列、重置生成批次，但不清空已执行动作记录；旧分支继续占容量。需求减少时不会删除历史分支，只会暂停生成超出当前容量的新动作。

树宽计算不读取 `node.visits`，所以它不是按 `sqrt(N)` 或访问次数增长的 progressive widening。使用 `--base-children-per-node` 和 `--max-children-per-node` 设置基础值与硬上限。结构化上下文无法提出更多不同需求时，即使反复访问节点也不会自动放宽。

## 记忆边界：只在同一个任务内

每次 `TaskRunner.run()` 都新建初始上下文、`TaskRuleStore` 与 MCTS；搜索开始时新建 `TaskKnowledgeBoard` 和搜索图。规则携带 `task_id`，跨任务读写会被拒绝。所谓“长程记忆”仅指同一道题内跨轮次、跨搜索分支的记忆，不是跨题学习。

任务结束后的规则和事实可以随评测结果保存，但不会作为下一道题的提示或规则库输入。API 请求只包含本次请求的系统提示与当前任务提示，不累积上一题的对话。公共提示前缀的 API 计算缓存也不等于把上一题经验加入下一题。

## 什么叫可用 recommend

优先级基于动作上的有效规则 ID，不是规则仓库是否非空：

- 规则属于当前任务，且适用当前工作区指纹；具体语义条件由模型在生成时判断。
- 动作没有执行过，对应方向没有被标记为已覆盖。
- 动作未被适用的精确 avoid 规则阻止；未知/过期规则 ID 不提供利用优先级。
- 节点可达且未终止、未耗尽，并且没有突破当前语义动作容量。

不强制把“普通 candidate 动作”算作推荐利用。无推荐时生成一个新的修复候选，仍属于探索替代方案；求解约束依然有效，不会退回无目的的目录扫描。

保留了原实现的一个边界行为：如果一批动作全部被经验性 avoid 阻止，允许保留一个作为探索兜底，但剥离 recommend 优先级，且环境层的命令约束不被绕过。recommend 探测最多一次不是“穷举所有可能动作后证明没有推荐”，而是当前有限候选与生成预算下的操作性判定。

## 保留了什么

RE-TRAC 结构化记忆、任务内 recommend/avoid 规则及其作用域、共享只读事实、同环境指纹下的语义节点合并、完整路径奖励回传、工作快照隔离、候选解保留与最终复验均保留。

没有为了融合而改写 UCB/奖励公式或增加新的研究评分：沿用原版覆盖率门控、recommend 衰减项和求解阶段关闭语义覆盖选择加分的规则。有效探索比例、知识复用率、工具冗余率仍只作事后统计，不用于在线选择。GRPO 部分仍是样本整理，不是已经接入了参数训练。

调度日志显示 `initial_exploration`、`recommend_exploitation` 或 `fallback_exploration`。最终 JSON、检查点与 SWE 的 agent-results 文件保存 `scheduling_trace`，可核对每轮在哪个节点执行了什么、用了哪些推荐规则。

## 本地验证（不调用 API）

在 PowerShell 中进入本项目目录：

```powershell
cd C:\Users\54177\Desktop\plore_ploit
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
python .\run_swebench_2tasks.py --dry-run --max-iterations 24 --max-tool-calls 80 --budget-multiplier 1
```

如 `python` 不在 PATH，请改用自己可用的 Python 3.11+ 完整路径。无需把本项目安装到两个原项目的 Python 环境里；Python 模块名为兼容入口继续使用 `cli_retrac_mcts`，安装时应使用独立虚拟环境。

`tests/test_plore_ploit.py` 覆盖语义树宽与访问次数解耦、3 到 6 的边界、任务间记忆隔离、初期探索、连续推荐利用、无推荐回退、规则作用域、图环路、预算感知与复验预留、弹性预算续算、硬上限，以及真实状态转移中的成功提前停止。证据依赖和按文件失效另由 `tests/test_semantic.py` 与 `tests/test_environment.py` 覆盖。

## 同样两道 SWE 题（只运行新项目）

新增开发评测入口：`run_terminal_bench_tenth.py` 从非冻结开发池抽取 1/10，`run_swebench_18tasks.py` 抽取 18 题；首次保存清单，后续直接复用，保持原冻结 9/50 题不变。完整 PowerShell 命令、清单复用和中断恢复见 [BENCHMARKS.md](BENCHMARKS.md)。

`run_swebench_2tasks.py` 固定使用此前两个项目的开发题：

- `sympy__sympy-16450`
- `matplotlib__matplotlib-20826`

Docker、WSL、SWE-bench harness 与 API 环境变量沿用原项目的配置。以下命令会实际消耗模型 API：

```powershell
cd C:\Users\54177\Desktop\plore_ploit
python .\run_swebench_2tasks.py --provider deepseek --max-iterations 24 --max-tool-calls 80 --budget-multiplier 1 --base-children-per-node 3 --max-children-per-node 6
```

脚本不会启动另两个项目或自动做对照。默认生成带 `plore-ploit-two-` 的唯一运行名，结果位于本项目 `benchmark_results/swebench/`。可以指定 `--run-id`，但不要在同时运行的实验中复用同一个名字。

两个测试现在统一为基础 **24 轮 / 80 次工具调用**，包括 SWE 的 2题、18题及冻结测试入口。测试脚本和直接 Agent CLI 的 `--budget-multiplier` 默认均为 **1（不续算）**。原有复杂度调度不变：难题按 1.35 倍向上取整到 **33 轮 / 108 次工具调用**，简单题仍可按 0.9 倍下调到 22/72，不再额外续算到 4 倍。树宽和搜索策略不变。

运行在验证成功时立即停止；没有可执行动作会以 `search_exhausted` 停止；普通动作触及复验预留区会以 `verification_reserve_reached` 停止并复验已有候选；达到其他上限会以 `hard_iteration_budget_exhausted` 或 `hard_tool_call_budget_exhausted` 停止。弹性预算能力保留，但只有显式设置大于 1 的 `--budget-multiplier` 才启用，可能显著增加 API 成本。最终复验命令现在也计入 `total_tool_calls`，JSON 同时记录预留量和实际复验调用数。Terminal 默认整题重试为 0。修改文件不会影响已启动进程；如需切换预算，请先 Ctrl+C 停止旧运行，不要使用旧命令中的 4 倍续算参数。

终端输出平均交互轮次、官方通过率和四项研究指标宏平均。每题过程与四项研究指标在 `agent-results-*.json` 的 `post_hoc_indicators` 中；`interaction-summary-*.json` 提供轮次与指标汇总。平均交互轮次按真实环境转移计数，不包括模型重试；`agent_succeeded` 是内部 verified_success，不等同于 SWE 官方 resolved。官方结论以 `official-report-*.json` 为准。缺失记录不当作 0 计入平均值；只看内部成功任务的平均轮次不能单独证明效率提升。

本项目已通过离线单元测试，但未据此宣称 SWE 成功率提高；效果需要真实实验验证。
