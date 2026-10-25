# BestFGS v6 vs v7：8 题配对实验（2026-09-30）

用户授权：v6 对照组与 v7 实验组，各 8 题，共 16 次正式试验。不是 HAI 对 BestFGS。
从之前十二题的固定种子顺序中取前八题；不读取旧成绩筛题、不携带旧结果或任务内记忆。
两组题目、官方镜像 digest、任务/评分文件、模型和逐题预算完全相同。新建独立工作区。

对照：冻结的 `/var/tmp/lizh639-monitor-control-v6`。
实验：冻结的 `/var/tmp/lizh639-route-selection-v7`，开启 route_search。
不改动两个发布。试验目录的 arms/v6、arms/v7 是经过哈希核对的独立来源副本。
驱动在各自独立 Harbor 进程中选择对应 PYTHONPATH，准备阶段核对真实 import 来源。
两组均为 BestFGS，保留 v6 的监控、反馈、记忆及停滞控制可靠性功能。

Actor、Advisor、Monitor 均用既有 deepseek-flash，temperature=0、thinking disabled。
Actor 输出上限 4096，Advisor/Monitor 1536；全模型逻辑轮次上限 800、工具上限 600、
Advisor 最多 6 次、Monitor 最多 12 次，保留共同重试策略与 48000 字符 Actor 上下文。
v7 探针、试做、检查与恢复占用原预算，不增加次数或时间。
只提供官方二元拒绝反馈，保持同一会话继续；没有隐藏评分信息传给模型。

共同题目（保持原顺序）：

1. spot-scheduler-traces：10800 秒。
2. modflow6-groundwater-regression-audit：3600 秒。
3. foldseek-paper-reproduction：3600 秒。
4. gdal-proj-raster-regression：3600 秒。
5. climate-netcdf-extreme-event-audit：3600 秒。
6. great-expectations-audit：3600 秒。
7. microscopy-cell-count-qc-audit：5400 秒。
8. epa-swmm-stormwater-regression-audit：3600 秒。

每组 agent 时间上限合计 10.5 小时，两组合计 21 小时；这是预算，不是预计必须耗时。
两条全局并发槽；逐题交替 v6/v7 的入队先后，各四题先入队。就绪槽异步调度，不保证严格锁步。
保留各题 CPU、内存、网络、评分器时限；共同预留 120 秒交付。原 900 秒普通命令上限不变。
v7 自身短探针/试做限制属于待评估算法策略，不单独放宽。

启动前：校验镜像/发布源码/任务文件、运行驱动与算法回归、两个真实 Docker 官方继续评测
夹具通过，然后封存全部输入哈希。准备和夹具使用脚本模型，不发生收费模型调用。
运行期间：独占启动锁、持久任务台账、外部超时和守护进程；已尝试的 trial 不自动重跑。
资源不足时暂停派发；凭据/余额故障和连续三个基础设施失败停止派发。保留问题和失败，不删除旧结果。
磁盘派发预留 120 GiB、执行硬底线 60 GiB；只清理本 trial 所有权标签匹配的临时容器。

密钥只经本地隐藏输入传入受限 tmpfs，不写进源码、任务容器、命令行或日志；结束后清理。
当前开始正式运行与否以 health.json / guard-started-v2.json 为准，不以此文档为准。

主要评价：配对官方分数/成功率。辅助评价：工具/模型/token/时间成本、后段监控覆盖、
条件失败路线避免重复投入、有效修改后公开验证、上下文感知重复率。记忆条数不作为成功指标。
单次 8 题是探索性对照，不据此宣布稳定优势；工程失败与解题失败分别保留。
