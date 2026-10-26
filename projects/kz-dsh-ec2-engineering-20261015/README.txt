KZ-on-DSH 0.3.1 / evidence-control-2 / engineering-1
独立工程修复副本，2026-10-15

原项目：../kz-dsh-ec2（只读参照；未部署、未停止其正在运行的实验）
当前目录：kz-dsh-ec2-engineering-20261015
算法行为仍为 evidence-control-2；新 storageRevision=engineering-1 不接受旧存储协议的检查点。
node_modules 为实体副本，不是指向原项目的链接。

修复
1. 必须有完整且顺序正确的 schema v2 生命周期收据；缺失、损坏、未完成、试次 ID 不匹配均不能算工程通过。
2. 清理分别记录 started/succeeded/failed；写审计失败仍尝试官方清理，不伪造成功。
3. 调度增加独立 trial_runner 收据；正在运行或结果不明的已派发试次暂停派发，不能自动重放。
4. 支持 inspect/reconcile/drain 和显式 resume；鉴权故障可先排空调度器，再以新凭据恢复剩余队列。
5. 检查点与事件日志使用可恢复事务；原始证据先持久化，内存事件提交成功后才清空；写盘失败后阻止新动作。
6. experiment.json 是冻结实验策略的唯一配置来源；协议生成/校验拒绝旧重试字段冲突。
7. 构建时显式指定 baseline release，将任务与代理复制入候选 dependencies；运行时不再引用历史 /var/tmp 目录。
8. 封存要求当前源码对应的 Linux 测试、新 schema 生命周期和对应 runtime 哈希；不能复用旧验收结论。

保持
前 10 题、并行 1、3 小时、首轮完成后工程故障统一重试一次、正常零分/有效预算耗尽不重试。
模型、门控、记忆、角色、冷却、压缩、请求/工具计数规则不变。所有已产生的试次和成本留在 admissions 中。

验收与发布
本目录的 deploy/terminalbench/ready.json 保持 passed=false。
audit/baseline-ec2 仅是旧版验收参考，不证明本版已通过真实 Harbor 验收。
最终本地 Linux 验证：377 项 Node、36 项 Python、2 项 deadline 全部通过，无跳过。
当前测试结论与原目录哈希核对记录见 audit/engineering/REPORT.txt。
付费启动和学院服务器部署均未执行。

后续独立部署（这些步骤不是本次已执行操作）
1. 本地 pack.py 生成 deployment.tar.gz，只含源码与部署脚本，不含凭据、历史会话或依赖。
2. 在新的 Linux 目录解包，为该目录单独准备 venv/bin/python 及与冻结版本一致的 Harbor 依赖。
3. prepare.py --baseline-release <显式指定的冻结基线目录> 生成本地任务/代理/运行包；基线只读。
4. 使用冻结 Node 执行 validate_offline.py --project runtime/kz --node runtime/node/bin/node。
5. 在该独立目录运行 accept_harbor.py（无模型验收），成功后 seal.py 才能给出 passed=true。
6. 任何付费试验启动需另行明确授权，凭据按原协议由启动进程标准输入提供，不写入命令行或文件。

运行中恢复操作（仅作用于这个部署目录）
campaign_admin.py inspect：只读查看状态。
campaign_admin.py drain：请求停止新派发，已在运行的试次继续到结束，不杀任务。
campaign_admin.py reconcile：持有调度锁核对退出收据，仅写对账报告，不启动任务。
campaign.py --resume：在新凭据通过标准输入提供且对账无歧义后启动新的调度进程；不会重放已完成试次。
未知状态的试次保持 blocked，需要查明外部实际状态；本版没有“强行当作失败再烧一次”的绕过入口。

限制
尚未证明真实模型效果或效率提升，也不解释旧 EC10 的所有失败。
本地 WSL 回归与真实官方容器生命周期验收是不同层级；只有后者及封存全部通过，才满足部署门禁。
