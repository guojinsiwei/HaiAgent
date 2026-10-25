# HAI / BestFGS 各六题：修复版配对试跑

本轮获用户授权：两个算法各跑六题。正式模型测试尚未启动，等待隐藏输入 API 密钥。

服务器目录：`/var/tmp/lizh639-lhtb-paired6-repair-v2-20260929`。
来源：`mechanism-conversation-fix-v2`，两算法共 60 个 Python 方法源文件与该修复版逐一核验一致。
原实验、原冻结源码和上一轮结果不改动；本轮不携带旧成绩。

## 配置

两算法使用完全相同的六题，取此前固定随机排序的前六题，不按旧成绩筛选。

| 任务 | 每算法 agent 时限 |
|---|---:|
| spot-scheduler-traces | 3 小时 |
| modflow6-groundwater-regression-audit | 1 小时 |
| foldseek-paper-reproduction | 1 小时 |
| gdal-proj-raster-regression | 1 小时 |
| climate-netcdf-extreme-event-audit | 1 小时 |
| great-expectations-audit | 1 小时 |

合计 12 次独立正式试验，全局并发 2。模型 `deepseek-flash`，原模型参数、工具和轮数预算、
任务镜像及官方评分器保留。每题均禁止自动重跑；失败和基础设施问题分别记录。
若全部跑满预算，约 8 小时 agent 工作时间，另加容器准备和评分开销；也可能提前结束。

## 启动前核验

- 镜像身份核验、方法源码核验和 12 个任务配置已生成。
- 38 项适配器/调度/审计等离线回归通过。
- BestFGS 和 HAI 的真实 Docker、官方评分器续跑 fixture 各通过，奖励均为 1，异常为空。
  这是脚本化链路检查，不是六题正式测试成绩。
- 封存完成，状态 `ready_awaiting_credential`；封存阶段 38 项适配器回归与 38 项 lean 回归均通过。
  协议哈希：`2d8bf206d995a561b47d5fe0f979d0bd11f467ede4c9ff9387ed80b8bbaaa67a`。
  完整状态见 `checks-status.json`；只有 `ready.json` 校验成功后才允许启动。
- 无真实模型调用；此前临时密钥已清除，本地环境也没有可用密钥。

## 隐藏输入启动

在本地 PowerShell 运行：

```powershell
& 'C:\Users\54177\Documents\ChatGPT\mcts\experiment_records\lhtb-paired6-repair-v2-20260929\Start-Paired6.ps1'
```

提示时输入 DeepSeek API 密钥，输入不会显示；不要把密钥发到聊天里。
脚本先核验封存和未启动状态，再通过 SSH stdin 传递密钥；云端仅放入权限受限的 tmpfs。
启动成功会返回 `launched: true` 和运行状态。若结果不明，先检查云端 `health.json`，不要重复启动。

结果以云端 `summary-v2.json`、`health.json` 和 `runs/` 内的官方报告为准。
这轮用于小样本行为和失败分析，不足以单独证明算法优劣或改动的因果收益。
