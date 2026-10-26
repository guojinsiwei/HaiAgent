DH 当前无工具修订候选：删除恢复拒绝硬停
日期：2026-10-08

基线：experiment_records/longcli-dh-tools-ablation40-repair1-20261008/sources/bestfgs-project。
运行器沿用 RoutedTaskRunner，子目标与1234开关保持原实验配置；不启用三个自定义工具。
仅修改 lean_runtime.py 与 rejection_recovery.py：
  - 删除“向导后再7次拒绝就结束整题”及结束原因重分类。
  - 第7次仍请求一次现有向导；同一个未解除卡点不会因此无限请求向导。
  - 相关变化/新证据仍可开启新的恢复阶段；全部调用仍受原角色及总预算约束。
  - 保留真实API鉴权/余额故障、请求/工具/时间预算、工程故障退出。
  - 重复动作门控、正交门控、记忆格式检查、Critic及回溯本次未修改。

本候选保留最近的上下文/执行工程源码；部署仍应沿用原实验公共适配器，
包括 SharedContextProjection 与 WireBudget/CheckedTransport，不能只运行裸核心
然后声称与原实验配置相同。

当前在线实验仍是旧的冻结版本。本修改不热替换运行进程，不修改已有结果，
不自动补跑/重新启动，也不声称修订后已获得新的真实模型分数。
历史 releases 与 experiment_records 的旧代码和验收证据保持不变。

代码入口：sources/bestfgs-project/src/bestfgs/lean_runtime.py
专项回归：tests/test_rejection_repair.py
负面控制审计：tests/test_negative_controls_audit.py
审计报告：AUDIT.txt（其余机制是发现的问题，不代表本次已修复）
验收：使用可写TEMP/TMP运行 python -B record_acceptance.py；不调用真实模型API。
