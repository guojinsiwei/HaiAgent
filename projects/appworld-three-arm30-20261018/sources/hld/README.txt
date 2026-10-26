HLD · 语义规划器候选版 · 0.4.0-semantic.2
2026-10-18

项目名称：HLD（npm 包名：hld）
本地目录：projects/HLD

实现目标
将探索的控制单位提升为跨多步的语义路线。每条路线描述一个假设、实现机制、
检查对象、行动步骤、进展信号和放弃条件。Solver 在当前路线上持续工作，
Monitor 或重复调用检测发现停滞后，Planner 更新语义路线滑动窗口。
每次唤起均新增 1–2 条路线，重新评估全部新旧候选，淘汰失效或低价值路线，
选择当前更适合执行的一条。普通工具调用无需逐条填写三维正交证明。

来源与隔离
基于 ../kz-dsh-exploration-v2-20261018/candidate/src 的本地副本实现。
旧 v2 的比较实验和部署目录保持原样。该目录是新的可运行候选源码，
没有远程部署，也没有启动付费模型实验。课题 DOCX 作为研究背景读取。
当前实现是结构化路线搜索；没有训练语义嵌入、奖励模型或强化学习策略。

执行链
任务 -> 侦查 -> 语义规划器 -> 当前路线 -> Solver 的多步执行 -> 公开检查
                                     ^                      |
                                     |-- Monitor/循环报警 --|
完成提交 -> 既有 Critic -> 补充验证/修复或完成审查

五个角色
语义规划器：解释任务与环境，保留未知项，每次生成 1–2 条新路线；
            联合评估新旧候选、淘汰并选取当前最合适路线，不直接执行命令。
Solver：侦查阶段先读任务、环境与验证入口；路线确定后执行诊断、实现和复测。
Monitor：评估执行及控制记录，提供有证据的停滞判断，继续管理条件性记忆。
Advisor/向导：给出局部困难的可选建议；建议交给 Planner 和 Solver 参考。
Critic：沿用 v2 的公开验收与缺口流程。路线切换不会关闭验收缺口。

启动与路线协议
1. 默认先收集 3 次不同动作的完整只读观察；重复同一读取、不完整输出和
   kz_update 等元数据调用不计数。此阶段限制实现动作；允许 read/glob/grep
   以及可识别的简单只读 shell 命令。侦查由现有 Solver 模型承担，无额外侦查角色。
2. 初始规划在下一次 Solver 请求前执行。Planner 接收原任务、实际观察、
   结构化上下文、子目标和已有记忆，返回任务解释、环境、未知项与 1–2 条新路线。
3. 初始路线为 D1、D2 等稳定 ID。每条包含 hypothesis、mechanism、target、
   steps、progress_signal、abandon_when、evidence_ids。路线定义保留在本题状态中。
4. Solver 可跨多步沿同一路线读写、修复与复测；修改相关输入后的原检查继续可用。
   可选测量探针、结果引用和显式重试仍使用 kz_strategy。原失败动作记忆继续生效。
5. 重复失败触发器、3 个近期控制拒绝或有当前路线证据的 Monitor 停滞判断
   请求重新规划。默认每 12 次路线动作也请求一次评估，该窗口本身不判定失败。
6. 每次唤起都必须新增 1–2 条路线，包含首次规划和保留当前路线的评估。
   evaluations 必须覆盖全部新旧候选：给出 suitability（0–1）、retain/retire、
   理由和证据引用，综合证据支持、预期进展、信息增益、成本、可行性及多样性。
   选择评分最高的可执行候选；评分相同时可进一步判断信息价值。评分为模型判断。
   遇到停滞须切换方向并给出宏观变化；定期窗口评估可继续当前有效路线。
7. 显式 retire 的路线退出窗口；容量溢出时按最新评分淘汰低分候选，平分时
   优先替换更旧候选。选中路线保留；新路线也可能因不适合当前任务被淘汰。
   默认窗口容量 12，包含当前路线；累计生成数量可以持续超过 12。
   未停滞的旧路线可继续竞争；已停滞路线不直接复用。单调递增 ID 防止回收旧 ID。
   保留最近 64 条淘汰摘要用于避免重复，完整路线和淘汰评估进入持久审计。
8. 每条实际动作在派发时绑定路线；迟到的后台结果仍归属原路线，包括已淘汰路线。观察、切换原因、
   路线定义和规划状态进入持久快照与审计。压缩面板只展示摘要，完整状态可通过
   kz_history {id:"context"} 分页读取。

边界与降级
- “宏观不同”的语义判断来自模型。程序检查字段一致性、ID、证据引用和精确重复，
  无法保证改写后的两条路线真正独立；实际采纳程度需要结合轨迹复核。
- 进展信号、放弃条件是给 Solver/Monitor 的语义指导，当前没有自动执行任意文本
  条件的判定器。路线绑定记录归属，不能独立证明每条动作遵循路线。
- Planner 的格式错误、不可用或预算不足都有显式记录；有剩余候选时按
  上次有效评分降级选择并标注未验证，无路线时保留普通执行能力。失败时不伪造新路线。默认间隔
  4 个恢复步骤才重试。连续侦查拒绝可提前用稀疏证据规划，未知项必须保留。
- 提前交卷最多得到两次侦查提醒；共享预算、取消与截止时间继续优先。
- 所有 Planner 请求经过已有 DSH 路由、请求/费用/时间预算，给下一次 Solver
  请求预留额度。Planner 不执行工具，不增加私有 API 客户端或独立解题循环。
- source 的配置默认保留旧模式以兼容库调用；本目录 config/kz.patch.yml
  已启用新模式。直接调用插件须显式传 semanticPlannerEnabled:true、full:true。

配置与使用
运行环境：Node >=24，固定 DSH 0.2.0-rc.2。本地 node_modules 链接到已有依赖；
复制到新机器后需要安装 package.json 指定依赖。
在本目录执行：
  node scripts/prepare-config.mjs
  node scripts/check-host.mjs
  npm run test:semantic
LongCLI 配置生成：
  node scripts/prepare-config.mjs --longcli --plugin-path /opt/semantic/src/plugin.mjs

生成 .runtime/kz.patch.yml 与 .runtime/transport.patch.yml，交由既有 DSH 启动入口
加载；设置独立的 KZ_WORKSPACE、KZ_AUDIT_DIR 和新会话，不复用 v2 检查点。
生成配置不会启动任务或付费请求。部署时仍需完成原有环境、预算与入口验收。

默认参数
semanticPlannerEnabled: true（交付配置）
semanticReconnaissanceSteps: 3
semanticRouteWindow: 12
semanticPlannerCooldown: 4
semanticMaxRoutes: 12（活跃窗口容量，允许持续更迭）
explorationEnabled:false 会一并关闭语义规划器；semanticPlannerEnabled:false
保留 v2 的单次探索模式，便于后续同配置消融比较。

验证与指标
专项测试覆盖初始侦查、跨步路线、基于证据的切换、后台归属、恢复、无效规划、
共享预算与真实 DSH AgentLoop 时序；模型和工具回执使用本地脚本化夹具。
最终数量、全量 v2 对照、共同失败列表和源码哈希见 VALIDATION.json。
全量历史测试含已有失败及跳过项，不能把专项通过写成整个仓库全部通过。

审计事件：semantic_planner_started、semantic_route_selected、semantic_route_action、
semantic_route_observation、semantic_route_switched、semantic_planner_unavailable、
semantic_route_evicted、semantic_window_updated。
route_coverage = 有实际派发动作的路线数 / 本题生成路线数；单纯选中不计覆盖。
该分母统计本题累计生成路线，淘汰不减少分母。规划调用数、切换数和公开检查进展均可复核；
这些指标没有自动证明语义空间覆盖、因果增益或官方任务成功。

关键源码
src/semantic-planner.mjs：路线协议、侦查门控、切换状态机、降级与审计。
src/full-integration.mjs：Planner 模型请求、Monitor 接入、共享预算及结束提醒。
src/plugin.mjs：实际工具派发归属、侦查门控、上下文提示与检查点版本。
src/full-task.mjs / structured-context.mjs：证据归属、持久状态与模型可见面板。
src/policy.mjs：保留原失败保护，语义模式解除逐次正交门控。
tests/semantic-planner.test.mjs / semantic-integration.test.mjs：专项测试。
