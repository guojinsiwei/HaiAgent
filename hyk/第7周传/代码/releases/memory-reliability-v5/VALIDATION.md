# v5 验证记录

- 云端完整离线回归：**308/308**；HAI 123、lean 38、提示视图 20、传输 32、
  修复及语义/记忆专项 77、分类 7、监督 11。较 v4 新增 21 项记忆可靠性测试。
  报告：`evidence/validation.json`，各组日志在同目录。
- 真实六题日志中两条被拒候选离线重放：**2/2 成功入库**。
  operation 的 123/143 字符不再导致核心经验丢弃，结论、条件、证据引用保持原样。
  缺少历史依赖快照，故适用性保留为需复查，不编造当前有效性。
  报告：`evidence/memory-replay.json`；原始候选及审计路径/哈希另存。
- HAI 源码 21 个 Python 文件与 v4 SHA-256 一致，未改 HAI 算法。
- 云端真实 Docker（Ubuntu 24.04）验收：**26/26**，新增五项均通过，FAIL/ERROR 均为 0，
  退出码 0，耗时 312.593 秒。完整证据：`evidence/run-20260930-111412-3f202503/`。
  新增检查覆盖观察记忆无需 LLM、无关修改仍适用、相关修改需复查、重复动作提醒和超长字段修复。
  清理记录 `cleanup_errors=[]`、`remaining_originals=[]`，独立查询无遗留专用容器。

上传初始包 SHA-256：`e15dc0cd0cd02776cf9cac31231c0f28c4cf78feecc853ba80d2377d2b756f5c`。
生产代码以 `fixed-source-manifest.json` 和 `integration-source-manifest.json` 为准；
说明文档与验证结果在运行完成后补充，不属于初始上传包。

云端部署：`/var/tmp/lizh639-mechanism-integration-20260929/repairs/memory-reliability-v5`。
没有修改原 trial、评分或 v4 发布。测试模型回复是确定性替身，外部模型调用为零；
本次未启动正式六题重测，不能据此宣称真实模型记忆使用率、任务分数或成本已经改善。
