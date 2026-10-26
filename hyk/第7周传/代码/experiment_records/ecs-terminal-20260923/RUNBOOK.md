# Terminal-Bench 云端 36 题配对实验

2026-09-23 15:20（北京时间）准备完成：36/36 环境通过；状态 `ready_for_deepseek_key`。
固定协议 SHA256：`5a861054448586272288ee3321aa026413b80ca914770a05e2c9269679b749ed`。
正式实验尚未启动，付费模型调用为 0。

## 启动门槛

只有云端 `paired_control.py status` 显示 `ready_for_key: true`，且
`control/preparation-final.json` 显示 `ready_for_deepseek_key`，才算准备完成。
预检阶段不进行付费模型调用，也不运行正式题目的验证器。合成测试仅验证自建任务。

在本机 PowerShell 执行本目录的 `Start-Terminal36.ps1`：先核验冻结文件，
然后隐藏输入 DeepSeek Key，通过 SSH 标准输入交给 ECS。不要把 Key 发到聊天里。
启动脚本会先做免费认证/模型可用性检查，再启动 72 次方法运行；此后才产生模型费用。
Key 不写入项目或任务 JSON，仅保存在云端 systemd 的临时凭据目录。

执行 `Check-Terminal36.ps1` 可手动查看进度。不启用定期 GPT 巡检。
启动确认后关闭本机不会停止云端 systemd 工作进程或 CubeStudio 下载隧道。
这不保证 ECS/CubeStudio 被关机、重建后自动恢复；中断任务不会被自动重付费运行。

## 固定设置

- 数据集：`terminal-bench/terminal-bench-2`，公开 89 题中排除冻结测试集 9 题。
- 随机种子 20260923，从剩余 80 题均匀打乱取 36 题；本次没有硬件筛选剔除。
- 同一 36 题，两种方法各一次，共 72 次；不因结果差或运行失败替换题目。
- 模型 `deepseek-flash`、官方 API、temperature 0.2，两组一致。
- 每题最多 24 次决策、80 次实际 CLI 调用，每个动作最多 6 条命令；不自适应扩容。
- 原题 agent/verifier 时间限制；两组同样预留 40 秒交付，不声称 token 消耗严格相等。
- BestFGS 为冻结 v12（经验/阻塞记忆/分支机制启用）；Raw 关闭这些机制。
- 普通交互历史、工具接口、独立 Python 和 CA 证书、任务镜像、评测器一致。
- ECS 4 核/16 GiB 上串行运行，题目位置交替决定先跑哪组；每次使用全新容器。
- 镜像锁定官方摘要。没有换成镜像站重打包的任务镜像。
- `/app` 文件快照可以恢复；外部 OS/服务状态不是完整容器回滚，属于本实验限制。
- 这是固定开发样本的探索性实验，不是整个 Terminal-Bench 榜单成绩。

## 指标与结果

- 成功要求官方 Harbor 验证器 reward=1 且没有评测异常，同时保存原始 reward；模型说“完成”不等于成功。
- 交互轮次 = 实际 CLI 反馈批次。另存模型决策次数、请求次数与 token usage。
- 工具冗余率沿用冻结 v12 的“可复用证据重复调用 / 实际 CLI 调用”口径；
  同时报告 unknown、完整轨迹覆盖和机械重复指标。不是人工真值，也不是因果节省率。
- 缺失评分/不完整轨迹不能填成成功或零成本；总体率会保留为空直到数据齐备。
- 不设置整题自动重试。模型正常失败保留；基础设施异常、磁盘不足、认证错误则暂停。
- 各组汇总保存在云端 `summary.json`，逐题日志保存在 `runs/`。

## 云端位置与安全

- ECS：`114.215.186.90`，`ecs-user`；实例 `i-bp1hxc4q30vih9j7qcwi`。
- 冻结算法：`/home/ecs-user/BestFGS-blocking-memory-v12`。
- 传输/调度：`/home/ecs-user/terminalbench-setup-20260923`。
- 实验根：`/home/ecs-user/terminalbench-paired36-20260923`。
- 云端服务：正式运行 `terminalbench-paired36`；准备 `terminalbench-preflight36-20260923`。
- CubeStudio 下载中继仅监听回环，限定公开软件域名，SSH key 仅允许对应反向隧道。
  桌面私钥没有上传；模型 API 不经过这个下载中继。
- TLS 证书验证始终开启。精简镜像缺少 CA 时，只给两组 agent 注入相同 Mozilla CA 包。
- 空间不足 20 GiB 时停止发起新任务，并在运行中每约 10 秒检查。
- ECS 持续计费；此前购买页面约 ¥29.60/天是报价，不是硬性消费上限。
  本次不创建更多付费资源、不升级配置、不自动释放实例。
