KZ 原生机制同步版 · 2026-10-19

入口：native/solve.py
版本：KZ-native-kzdsh-mechanism-sync-20261019
本地目录：projects/kz-native-mechanism-sync-20261019

范围
以 KZDSH 2026-10-18 exploration-v2 已完成版本为机制参照，补齐原生 KZ 的缺失机制。
原生 KZ 的 Python 任务循环、命令执行、模型桥接、时间与工具预算继续使用原框架。
保留原版 projects/kz-native-orthogonal-trigger-20261017，未覆盖历史实验。
HLD 的语义路线规划及另一聊天正在进行的 AppWorld 修复属于独立版本。
本次没有远程部署、启动模型实验、调用模型 API 或修改 KZDSH 实验目录。

机制对齐
1. 探索触发
   以声明目标、目标集合、诊断族聚合失败；pytest 展示参数变化保留同一检查身份。
   Monitor 的两个近期、完整、无公开通过检查的证据可以触发停滞探索。
   重复报警去重；不把成功执行改写成失败；退出后需新证据或条件变化才重新武装。
2. 探索测量与学习
   同一 JSON 标量的互补预测；要求假设、替代解释、测量方法。
   缺失、类型错误、冲突、不完整输出保留 unknown；文字命中只作观察。
   结果记录保留证据、条件和不确定性；下一探针必须引用同轮上次结果。
   普通读取/修复可以携带可选结果引用，实际派发与实际回执分别记录。
3. 门控与退出
   结构化测量可复用命令词汇，TF-IDF 只作遥测；原样失败动作仍受最终重复守卫约束。
   8 次探针或 16 次实际动作或连续 2 次格式拒绝后关闭门控，4 步冷却。
   不注入自动诊断命令；超时、取消、不完整执行不能沉淀为稳定失败锚点。
4. 子目标
   可以先登记目标、后补检查；显式修订有版本号、理由和历史记录。
   实质静默测试可用 stdout_contains:[]、exit_code:0；echo/true 和空跑不通过。
   实际匹配的检查自动验收；当前回执可显式绑定；新失败、文件变化或目标修订撤销旧证明。
   验证专用身份忽略描述文字，保留目录、输入、环境和时限差异。
5. 完成审查
   Critic 检查必须引用公开要求、说明预期值来源，并提供实际执行回执。
   完成缺口使用稳定 ID、明确关闭证据；遗漏缺口或改写措辞不能让它消失。
   保留不同观察的摘要，A→B→A 不会丢失 B；相同证据不重复购买审查。
   无实际活动的重复提交以 incomplete_repeated_submission 结束，submitted=false。
   缓存限显式工作区检查，要求文件指纹一致、无中间观察；fresh:true 强制重验。
6. 记忆、过滤与共享控制
   保留证据绑定、依赖条件、相关检索、独立记忆预留、历史原文检索、终端投影和任务隔离。
   补齐实际动作命中的可见 blocker 审阅覆盖，避免只审阅无关记忆。
   Actor、Monitor、Advisor、Critic 继续计入同一请求/工具/时间预算及原生费用账本。
   凭据和余额故障门闩、局部纠错、侦察、回溯冻结继续沿用。

原生执行边界
原生环境保持同步命令和进程组收尾；DSH 后台作业宿主 API、会话存储和压缩实现保留在 DSH。
此次对齐针对机制行为及证据条件，两个运行框架的工具接口和存储格式仍各自保留。
默认实验预算参数沿用原生配置，没有因为同步机制增加额度。
本版本要求新任务和新审计目录，不能把旧任务检查点作为新版状态恢复。

验证
Linux/WSL 运行：python3 validate_offline.py
专项运行：python3 -m unittest discover -s native -p test_mechanism_parity.py -v
整体结果见 VALIDATION.json、audit/offline-summary.json 和 audit/offline-tests.log。
原生与 KZDSH 的 21 组测量用例逐字段一致：audit/measurement-parity.json。
原版 33 项 legacy test_lean 有 5 项历史失败，失败名称已与本版逐项比较。
这些失败继续保留，未删断言或改成跳过；全集命令因此仍返回非零。
更早期 test_v17_reliability/test_prompt_views 依赖未随原生包携带的 examples，
不计入本次 105 项可执行回归；其导入限制保留在版本说明中。
当前原生记忆、输出过滤与历史检索另有专项行为验证。
离线检查通过不能证明 benchmark 分数或真实模型采纳得到改善。

追溯
BASELINE-MANIFEST.json：修改前原生包的文件哈希。
SOURCE-MANIFEST.json：本次最终代码、测试和说明的文件哈希。
PROVENANCE.json：参照 KZDSH 文件哈希、机制映射与版本边界。
audit/source-change.diff：相对原生候选的完整文本改动。
