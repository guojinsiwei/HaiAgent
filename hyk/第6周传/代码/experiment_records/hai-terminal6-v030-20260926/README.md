# HAIAgent 0.3.0 Terminal-Bench 配对重启

- 学院节点：lizh639@172.16.108.236。
- 云端目录：/mnt/sdb/home/lizh639/hai-terminal6-v030-20260926。
- 使用原固定 6 题；HAI 与 Raw 各 6 次，总计 12 次，串行、交替方法顺序。
- 模型 deepseek-flash，官方 API，原生 choose_action 工具调用；两组显式 thinking=disabled。
- 连续 3 次或累计 8 次格式错误停止本题并阻止调度继续；不自动整题重跑。
- 每题沿用公开任务墙钟预算；80 轮、70 工具调用；指标口径不变。
- 旧 0.2.0 实验暂停封存，不混合统计，不恢复其轨迹。
- 成功依据官方 Harbor verifier；离线 fixture 仅验证基础设施，不是模型成功。
- 本机 Start-HAIPilot.ps1 隐藏输入 Key，经 SSH 标准输入传递；短暂存入远端私有 /dev/shm 目录，worker 读取后删除。
- worker 在 tmux 内运行，断开本机不会中断，但节点故障仍会影响实验；不启用 Codex 定时巡检。
- 没有凭据前不会启动模型调用。ready.json 表示零调用预检通过，不表示付费实验已启动。

本机 PowerShell 启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\54177\Documents\ChatGPT\mcts\experiment_records\hai-terminal6-v030-20260926\Start-HAIPilot.ps1"
```

不要重复启动；如启动报错，先检查 health.json 和 worker.log。原已启动记录会阻止无意重跑。
