# LHTB 三组实验：阶段性失败归因（2026-09-28）

本报告只读审计既有实验，没有更改算法、题目、预算或正在运行的补跑。数据来自学院节点 `172.16.108.236`，不是模型自述成功。

## 1. 比较口径

汇总来源：`/var/tmp/lizh639-lhtb-r4/summary-v2.json`。12 题 × 3 方法共 36 行，其中 34 行有官方 reward；great-expectations-audit 的 BestFGS、Raw 原运行缺失官方分数，正在 `/var/tmp/lizh639-lhtb-missing2-r5` 补跑。

以下均分只使用三组都有官方分数的同一组 11 题。reward 是连续分数，不能称为任务成功率。

| 任务 | BestFGS | HAI | Raw |
|---|---:|---:|---:|
| spot-scheduler-traces | 0 | 0 | 0.8133 |
| modflow6-groundwater-regression-audit | 0 | 0 | 0 |
| foldseek-paper-reproduction | 0.3333333333 | 0.3333333333 | 0.3333333333 |
| gdal-proj-raster-regression | 0.0004833253 | 0 | 0 |
| climate-netcdf-extreme-event-audit | 0.0666213074 | 0.0666213074 | 0.0666213074 |
| microscopy-cell-count-qc-audit | 0 | 0.05125 | 0.05125 |
| epa-swmm-stormwater-regression-audit | 0 | 0 | 0 |
| satellite-flood-change-detection-audit | 0.0933333333 | 0.0933333333 | 0.0933333333 |
| opensees-seismic-structural-regression-audit | 0.0005927682 | 0 | 0 |
| unison-paper-reproduction | 0.1666666667 | 0.1666666667 | 0.1666666667 |
| matpower-opf-regression | 0 | 0 | 0 |
| **均分（11题）** | **0.0600937031** | **0.0646549673** | **0.1385913310** |

Raw 与 HAI 在 10/11 题完全同分，全部累计分差来自 spot。BestFGS 对 Raw 为 2 题略高、2 题较低、7 题同分，差距也主要来自 spot。不能据此推出 Raw 在所有任务上普遍更强，更不能推出记忆本身无效。

## 2. BestFGS：评估已识别退化，但候选交付没有尊重该证据

证据目录：`/mnt/sdb/home/lizh639/lhtb-triple12-v161-20260927-r2/runs/bestfgs-spot-scheduler-traces/spot-scheduler-traces__3xQZpMr/agent/`。

- `audit.jsonl` 工具调用 304（seq 1592）：将 `SchedulerPolicy.step` 改为 `pass`，原实现移到 `_unused_step`，动作目的明确写着临时占位修改。
- 工具调用 305（seq 1593）：公开模拟输出 Deadline met 0/100、Normalized 0.0000，但进程退出码是 0。
- seq 1595 的 assessment 正确指出 step 返回 None、策略已损坏、相对先前表现发生回归，应先修复。
- 最终 `graph.json.best_workspace` 指向快照 `2c936d64e3434468ba400f5ffd4bbc65`；其 `workspace/policy.py` 的 step 仍是 `pass`。
- 同一快照还保留了 overall_score 0.8326 的旧 `output/simulation_results.json`。这个文件不是当前代码表现的可靠证据，不能当作当前候选的真实分数。
- `graph.json.delivery` 却记录 `local_validation_passed=true`、`selection_reason=latest_publicly_validated_candidate`、`final_verification_status=not_run`；`submitted=false`。审计末尾 `method_end` 为 `wall_budget_exhausted`。

源码对应：冻结副本 `bestfgs-project/src/bestfgs/models.py:426` 的 functional_validation_succeeded 基于命令 succeeded；`best_first_runtime.py:1604` 一带据此登记候选；`CandidateRegistry.best_verified` 按登记顺序选最新，而非任务得分最大。此题的 verifier 只把 simulate 的退出码传回来，未对任务表现作断言。

结论：这是“命令执行成功”被当成“候选功能通过”的验证契约缺陷，加上最终选择/墙钟兜底问题。不是评估模型完全不懂；它准确说出了错误，但其语义失败证据没有有效阻止坏候选交付。中途确有非零公开模拟结果，但不据此声称有一个候选已通过官方评测。

## 3. HAI：路径作用域切换清空重复计数

证据目录：`/mnt/sdb/home/lizh639/lhtb-triple25-v161-20260926/runs/hai-spot-scheduler-traces/spot-scheduler-traces__JVDQx7E/agent/`。

- 600 次工具调用中，同一读取 trace 统计的 bash/python 命令出现 583 次，返回相同 72 字节统计结果，工作区 revision 稳定。
- 日志没有 automatic_memory、repetition_observed、repeat_decision；末尾 memory_count=0、decision_advice_visible=false。
- 动作 cwd 是 `/app`。`haiagent/runtime.py:320` observe 时使用动作 cwd；`:338` 随后将上下文 scope 重设到宿主镜像 workspace。
- `terminal_context/stagnation.py` 在 cwd/workspace/environment 任一 scope 改变时清空 entries。因此 `/app` 与宿主镜像路径的往复切换让同一命令的计数无法积累。
- 对远端同一 RepetitionTracker 做无文件写入、无 API 的 5 次重复复现：使用 `/app` 并每次切回镜像根目录，检测结果为 `[false,false,false,false,false]`；始终使用同一根目录为 `[false,false,true,true,true]`。

结论：该题主要不是模型拒绝使用记忆，而是路径别名与作用域集成缺陷导致重复记忆根本没有形成。

## 4. HAI：阻止工具重复不等于打破决策循环

证据目录：`/var/tmp/lizh639-lhtb-r4/runs/hai-microscopy-cell-count-qc-audit/microscopy-cell-count-qc-audit__fTSBSTC/agent/`。

- 800 轮模型响应，只有 24 次工具执行。
- 第 25 至 800 轮共 776 次 repeat_decision，executed=false、retry_reason=null。
- 检测生成 M1；后续提示中 decision_advice_visible=true，包含重复证据及更换方案/给出重试理由的提示。完整 task_memory 在所查请求中因预算未选入，但紧凑 advice 确实存在。
- 模型持续请求同一图像连通区域检查；控制器持续拒绝，直到耗尽 turn_budget。

结论：反馈已到达模型，但系统没有在持续拒绝后进入有效恢复路径。工具层循环转成模型层循环，不能把工具调用次数降低直接解释为效率改善。

## 5. BestFGS：职责拆分没有消除管理成本

spot 的逻辑 model_request：action 401、assessment 253、memory 233，共 887；非 action 占约 54.8%。这些是包装层角色调用，不等于底层 HTTP 请求次数。

各角色最后一次成功返回附带的 cumulative_usage：

| 角色 | api_requests | completion_tokens |
|---|---:|---:|
| action | 410 | 868984 |
| assessment | 253 | 78832 |
| memory | 317 | 1123466 |

这些是最后可见累计值，不保证覆盖最后一次失败请求。memory 的 failure_counts.output_length=119；包装层 memory 的 model_error 为 42 次，二者统计层级不同，不可相加。

角色分离实现仍是串行调用。该题约 178 分钟后墙钟耗尽，451 次工具调用，尚未用完 600 工具预算。记忆角色输出比动作角色还多，表明记忆维护已经成为显著负担，但不能无消融地声称它解释全部得分差。

## 6. Raw 同样严重重复，不能把它描述成会合理停止

spot Raw 在工具调用 12 就写出简单的“有 spot 则使用，否则 on-demand”策略，公开模拟得到非零分。后续同一写入/模拟命令仍重复 203 次。官方最终 reward 0.8133。

Raw 的优势在于先留下了有效产物，不是它没有循环。该题 Raw 还以 INFRASTRUCTURE_ERROR 结束，不是正常 submit。unison Raw 也有基础设施终止；climate Raw 与 opensees HAI 有 protocol_error。

所以：有官方 reward 只说明残留产物被评分，不能证明运行过程全部健康。本报告没有查明上述每个基础设施异常的底层原因，不把这些异常全部归因于算法。

## 7. 后续优先级（本轮未实施）

1. 修复候选验证契约与选择：明确区分命令退出成功、行为正确、任务分数；验证证据绑定当前代码，公开性能明确退化不能继承通过状态；墙钟到期仍交付可信保底产物。
2. 修复 HAI 路径别名归一化及计数作用域；保留真正环境变化时的失效机制。
3. 为连续重复拒绝设计有界恢复：改变决策信息/策略、限定额外尝试、必要时明确失败终止；不能只是无限返回同一拒绝提示。
4. 缩小并限制记忆更新输出，事件触发增量更新；统计串行管理时间、全部角色 token、解析重试成本。
5. 用这些既有失败轨迹做无付费回归，再冻结新版本开展同题比较；不要修改当前补跑造成混用。

本次最后读取补跑 health.json：running，2 个 active、0/2 completed、problems=[]、free_gib=234.22。此状态只代表检查时点，不是长期在线保证。
