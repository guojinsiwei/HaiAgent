Recuris historical frozen on DSH — 0.1.0

入口：src/plugin.mjs。算法：worker.py + vendor/recuris 的原历史模块。
共享宿主、配置、验收与说明：../dsh-baselines/README.txt。

范围经用户确认：固定 E/W/rho/C 包，题内 W 可更新；不启用 Meta、TTA、
跨题训练或测试题经验积累。它是历史 Recuris-Frozen 的 DSH 适配变体，
不是完整论文方法，也不是作者 Harbor 原样执行。

保留原历史 memory.py / working.py / prompts.py / protocol.py / response_text.py；
lock.mjs 会校验它们与实际历史目录逐字相同。作者只读源码快照与许可证
在 vendor/upstream；固定通用种子在 vendor/terminal_seed.json。

DSH 负责 Actor 的请求、循环、原生工具、权限、会话与压缩。
worker 只处理 W 初始化/更新、E 检索与 C 提交，不执行 shell，不建立模型客户端。
辅助角色的请求通过父进程 ctx.llm.stream，使用完整原任务与共同模型配置。
recuris_verify 绑定目标 ID 后委托 DSH 原生 bash；元数据与实际 bash 分开计数。
格式恢复只消耗共同 API/时间预算，没有新增两次拒绝退出规则。
recuris_stop 用于明确报告未完成，不能把工程错误改写成正常完成。

验收只证明机制和工程链路工作，不证明算法效果或与原论文得分等价。
