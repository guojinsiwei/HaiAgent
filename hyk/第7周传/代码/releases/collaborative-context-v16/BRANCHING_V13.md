# BestFGS v13：恢复原有全局分支搜索

v13 从 `blocking-memory-v12` 独立复制，不修改正在运行的 v12。

## 核心决定

- BestFGS 默认重新使用 `phase_adaptive_semantic_best_first`。
- 每个候选动作从父快照创建隔离分支；旧分支、候选补丁和分支局部证据不会因切换方向而丢失。
- 全局前沿综合真实进展、信息增益、候选成熟度、失败与重复代价选择下一条边，不强制围绕当前候选顺序推进。
- 初始语义地图仍只执行一个 bootstrap 动作；后续根据真实反馈扩展不同语义方向，不做同层 Beam 批量执行。
- conditioned 任务内经验、细粒度匹配、交付门槛、候选保留、最终复验和指标实现全部沿用 v12。
- v12 的顺序 evidence/阻塞记忆运行时仍保留为显式消融入口，但不是 v13 BestFGS 主路径。
- Raw 基线继续使用纯顺序 CLI：无经验、无分支、无阻塞控制。

## 入口

直接运行 `python -m bestfgs` 默认等价于 `--engine graph`。
`--engine legacy` 是同一图搜索入口的兼容别名；`--engine evidence` 显式选择 v12 顺序证据控制器。

配对实验的 `run_comparison.py` 为两组冻结不同入口：

- `bestfgs`: graph + conditioned experience
- `raw`: evidence controller + experience off + branching off

两组仍共享模型、任务、工具/决策预算、任务环境、交付格式和官方评测流程。图搜索和顺序基线的提示上下文大小不会被错误宣称为等 token 预算，模型用量必须单独报告。

## 为什么阻塞记忆在主路径关闭

v12 的 blocker 是为顺序控制器设计的“替换当前批次”机制。未经重新定义就插入全局图前沿，会把诊断/暂缓错误记成普通搜索边并影响候选优先级。v13 先忠实恢复原有分支算法；阻塞记忆保留作独立消融，而不静默混入主方法。若后续要组合，应先为 blocker 设计图搜索原生的边状态和预算记账，再单独验证。
