# LongCLI：Planner/Solver 图搜索 v3，10 题

本轮只运行一个新方法 `planner-v3`，沿用上一轮固定的 LongCLI 10 题和原始公共输入，不复用解题产物，也不重跑 RAW。

- 模型：四个角色均 `deepseek-flash`，thinking 关闭，temperature=0。
- 每题共享：800 次逻辑模型请求，600 次工具调用；前 8 题 2 小时，AP 两题 3 小时。
- 图容量沿用候选版本：64 节点、64 快照、宽度 2、每节点最多扩展 2 次。图容量可能先于工具预算耗尽，停止原因必须单独报告。
- Planner 上限 24 次尝试；Advisor 6 次；Monitor 12 次，全部计入总模型预算。
- 解题：Cube 两容器 31081/31121，各 5 题、各 2 并发，总并发 4。
- 评分：学院服务器全新 Docker 实例，单个最终产物官方评测一次，评分并发 1。
- 密钥：用户本地隐藏输入，经 SSH 标准输入送达；远端仅在私有 `/dev/shm` 临时凭据中保存，worker 结束后删除，不写入运行参数或审计日志。

任务：scheme、ants、cats、hog、hw08、cmu p0/p1/p2、ap hw26/hw35。正式 ID 与不可变镜像 ID 见 `protocol.json`。

## 运行入口

`Start-PlannerV3-10.ps1` 会先验证源码封存和独立评分输入，再询问密钥、启动两个 worker，并启动本地无模型的结果搬运与评分脚本。运行可用：

```powershell
powershell.exe -NoExit -ExecutionPolicy Bypass -File "C:\Users\54177\Documents\ChatGPT\mcts\experiment_records\longcli-planner-v3-10-20261004\Start-PlannerV3-10.ps1"
```

ExecutionPolicy Bypass 只对该进程生效，不改系统策略。不要重复运行已启动的 worker；脚本也会拒绝重新认领。

## 验收与隔离

正式题根目录均新建。先对分配的全部 10 题做零 API 验收：`/dev/null`、无网络/主机目录/隐藏测试、管道失败识别、文件恢复、C++ 工具链，以及真实 Planner/Solver 两兄弟分支回溯、清理夹具、导出产物。验收与付费运行使用不同目录。

Solver 仅接触公共任务文件。隐藏测试和官方评分器只在学院侧使用；不向解题者反馈中间评分。已知 Cats starter 缺失 `READMD.md` 的原生 P2P 问题保留，不能把它归因于本版。

远端解题目录：`/mnt/lizh639/longcli-planner-v3-10-20261004`。
学院评分目录：`/var/tmp/lizh639-longcli-planner-v3-10-20261004`。

本地 `paired-status.json` 汇总生成/评分；`received/` 收取每题结果和日志。名称沿用可靠的旧收集器，本轮实际为单组 10 题。

**本地电脑需要联网、保持运行，自动回传与触发评分才会推进。** 云端 worker 不依赖本地窗口保持打开；本地断网不表示解题停止。评分认领和失败不会自动重跑。没有创建消耗 GPT 额度的巡检任务。
