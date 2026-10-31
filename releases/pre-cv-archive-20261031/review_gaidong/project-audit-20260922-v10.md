# 当前 BestFGS v10 项目审计

日期：2026-09-22。审计范围是 `releases/redundancy-metric-v10` 的经验、搜索、验证交付、指标链路，以及 `experiment_records/swe-v10-current50-20260921-01` 的双容器调度脚本。没有逐一审计历史副本，也没有修改冻结代码、重启实验、调用模型或启动官方评测。

本地实现指纹为 `39982dace76e1a54e6db69f32eb9087609b7a18f642129af29362c3731a84f1f`，与本次云实验协议中记录的实现指纹一致。协议指纹为 `baeebabad4e1b74a0877706ecaa3e68b7b0a538c68b9b6c3f2a785c78611ccee`。

以下严重性表示建议修复顺序。离线复现证明缺陷可以触发，不表示已证明它们在本次每一道 SWE 题上发生，也不能直接据此估算成功率损失。

## 1. P1：条件经验被检索后，仍可能在提示词投影时丢失

定位：`src/bestfgs/retrac_adapter.py:1879`、`:1889`；`src/bestfgs/micro_experience.py:413`；暴露计数在 `src/bestfgs/best_first_runtime.py:1929`。

用现有 `MicroExperienceStoreTests.observe_failure()` 构造失败观察，检索得到 observation、conditional_hypothesis、hypothesis。三者单独投影分别约 1251、1518、1033 字符。传入真实 `_project_rules_for_prompt(rules)` 后只剩 observation 与 hypothesis，条件微经验被省略。

原因：2500 字符总预算只按顺序容纳整条记录；压缩仅在单条大于 2498 字符时触发。检索排序与最终提示词预算没有共同保障条件经验的可见性。运行时的 exposed 计数又发生在投影前，不能代表模型真正看到了多少经验。

建议：按最终可见预算联合筛选、压缩和合并同源经验；记录实际进入模型的经验 ID。补充完整 rules → 真实 adapter 提示词测试，而不是只测单条规则或直接接收裸 rules 的脚本策略。

## 2. P1：验证临时补回源码后可通过，但导出补丁仍然缺失源码

定位：`src/bestfgs/environment.py:466`；提交资格检查在 `src/bestfgs/best_first_runtime.py:1342`。

验证只检查 baseline 中原本存在的文件是否被改变，没有检查新增文件。真实 Git/Python 离线复现：候选删除 `answer.py`；验证在临时副本补回正确的 `answer.py` 并运行公开测试；只读提交后得到 `submitted=true`、`local_validation_passed=true`，但候选仍然缺失该文件，导出补丁只是删除它。

建议：检查验证前后路径并集，至少禁止验证补回基础仓库中被候选删除的源码。允许的编译产物和报告应与实现文件、配置区分，不能简单全面禁止新增文件。新增“删除源码 → 验证补回 → 提交”的端到端回归。

现有 `tests/test_environment.py:191` 仅覆盖改写已存在源码，另有测试要求允许生成编译产物，未覆盖此反例。

## 3. P2：新候选可凭更弱的测试替代旧候选

定位：`src/bestfgs/best_first_runtime.py:413`、`:432`、`:2698`、`:2734`。

候选主要按 sequence 新旧排序，终验重跑各自登记的 verification_commands。离线复现：旧候选 `VALUE=1` 通过关键修复检查与类型检查；新候选 `VALUE=2` 只通过类型检查；最终选新候选并标记本地验证通过，补跑旧关键检查立即失败。

建议：维护仍适用的任务级公开回归要求，候选修改相同实现后不能省略已建立的关键检查。更强候选的判定不应简单等于“更新”或“命令更多”。失败后回退测试不能替代验证范围缩窄的测试。

## 4. P2：执行层与经验层对同一绝对路径解释不同

定位：`src/bestfgs/experience.py:321`；`src/bestfgs/environment.py:532`、`:596`。

实际执行会将种子工作区绝对路径重写成当前快照路径，但经验层使用原始 CommandSpec 对最终快照求依赖，导致允许的种子别名被误当作外部依赖。

真实环境离线复现：相对路径 rg 和种子绝对路径 rg 都读到相同内容；前者 dependency_status=known、可阻止重复，后者 unknown、不能阻止。公开失败检查 `python check.py` 产生一条可复验义务，同一脚本使用种子绝对路径后产生零条。

建议：执行、经验、冗余检测共用可信路径映射，记录可重新绑定到快照的规范命令。仅接受已知别名，不应把任意外部绝对路径视为任务内依赖。

## 5. P1（指标有效性）：实际调用与冗余检测覆盖严重不匹配

定位：`src/bestfgs/redundancy.py:148`、`:170`、`:190`、`:280`。

只读汇总审计时已完成的 40 题：

| 分类 | 次数 |
| --- | ---: |
| 全部已结束工具调用 | 2001 |
| unknown | 1888 |
| nonredundant | 107 |
| redundant | 6 |

可判定覆盖率只有 5.65%。6/2001=0.30% 是检测到的冗余比例，不能当作真实冗余很低的证据。1888 次 unknown 中，1876 次使用同一原因 `unsupported_or_unobserved_dependencies`，12 次为 `incomplete_or_blocked_observation`。

离线复现：简单 Python 文件读取可以识别，但添加 `encoding='utf-8'` 或对读取结果切片就不识别。所有 stdin 命令也不可识别。现有记录又把不支持语法、依赖缺失、证据变化等原因混在一起，无法仅凭汇总确认真实各类原因的占比。

建议：先细分拒绝原因和命令类型，再针对真实高频、安全可观测的形式扩展检测。保持 unknown 的独立状态。当前冻结实验原指标应保留；任何新离线审计口径都应另行标版本，并先确认旧轨迹足够支持重算。

两个额外已复现的指标缺陷：

- `redundancy.py:291` 对成功输出也按 connection/network/timeout 等裸子串筛选，测试名 `test_connection PASSED` 会使重复检查变 unknown；本次40题该原因计数为零，因此不是当前低覆盖的主要原因。
- `compare_experiments.py:28` 的完整性门槛缺少新冗余字段校验；删掉 redundancy_version 和 redundancy_unknown_calls 后，报告仍可出现 valid_complete_protocol=true 和 repeat_rate_micro=0.25，同时新指标为 null。应统一新指标校验与旧别名可用性。

## 6. P2：无验证命令也复制仓库；指标扫描开销高

定位：`src/bestfgs/environment.py:403`、`:410`、`:442`；`src/bestfgs/experiment_metrics.py:85`、`:115`。

离线复现一条只读命令，verification_commands 为空、预算还有余量：仍发生两次完整工作区复制和三次全树清单/哈希计算，其中一次副本仅用于执行零条验证命令。

真实已完成40题轨迹中 instrumentation_seconds 累计 5977.0 秒，工具 duration_seconds 累计 2062.6 秒，前者约为后者的2.9倍。这是跨题累计，不是墙钟时间，也不包括所有复制/记忆开销；不能据此认定全部运行瓶颈，但足以支持减少无用扫描的优先级。

建议：空验证直接返回，执行流程中复用确定未变化的清单；进一步优化需保留源码与权限/符号链接变化的正确检测，不直接以 mtime 替代内容校验。

## 7. P2：状态查询会失败，也会误报另一台容器会话死亡

定位：`experiment_records/swe-v10-current50-20260921-01/remote_current50.py:371`、`:384`，以及 `Check-Current50.ps1:3`。

已通过只读检查确认：

- status 分支没有初始化导入路径；随附 PowerShell 检查脚本也没设置 PYTHONPATH。存在轨迹时执行出现 ModuleNotFoundError。
- 查询在容器1本地检查 worker-0 与 worker-1 的 tmux socket，因此汇总显示 worker-1=false；直接在容器2检查 worker-1 返回退出码0，会话实际存活。

建议：查询入口显式初始化依赖路径；各容器检查自己的进程和会话，再聚合结果。共享心跳应展示观测主机与观测时间，不能把未在本机找到远端进程解释为死亡。

## 建议实施顺序

1. 验证与交付一致性：临时补源码漏洞、保留适用回归检查。
2. 经验是否真正到达模型：最终可见经验计数、预算分配、路径归一化。
3. 指标覆盖与原因分类，并修正报告完整性校验。
4. 去掉空验证复制、减少重复扫描，修复监控显示。

这些发现支持先修已有机制之间的连接与可观测性；尚不支持认定树搜索框架整体无效或需要增加新的算法机制。修复应在新版本离线回归和小规模消融，当前50题保留冻结口径并完成独立官方评测。
