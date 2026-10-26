# v2 会话修复验证

本地和云端相关回归均为 **233/233 PASS**。其中新增会话测试 11 项；其他包括
HAI 123、BestFGS lean/Docker 38、提示视图 20、传输 32、v1 专项 9。

Ubuntu 和 MATPOWER 真实 Docker 完整集成测试各 **15/15 PASS**，均退出码 0，清理错误为零：

- Ubuntu：`run-20260929-215121-7bb5890e`，244.425 秒。
- MATPOWER：`run-20260929-215612-8e34a74d`，288.425 秒。

两轮运行的资源归属记录均已清空，完整结果与请求记录已回收至工作区。

新增传输层检查使用实际请求编码，只模拟 HTTP 返回：第十步后请求仍有 10 个
历史 assistant 回合与第一步真实输出，而近期面板已没有该输出；之后通过历史
检索取回该回合，结果出现在下一次请求。最大消息体 21584 字符，低于原 48000
字符预算。没有真实模型 API 请求。

部署目录：
`/var/tmp/lizh639-mechanism-integration-20260929/repairs/mechanism-conversation-fix-v2`。
上传包 SHA-256：`92ce631991657882bf62977a1cbeab9dad4d61c5c6ee0babad872c9e19be043a`。
原冻结版本和此前 v1 部署未改动；正式实验入口未切换。

工作区完整记录：`experiment_records/cloud-conversation-repair-20260929/REPORT.md`。
完整请求消息保存在各 run 目录的 `best-conversation-wire/wire-requests.json`。
这证明上下文信息确实进入传输，而非只在宿主日志中留存；不证明真实模型收益。
