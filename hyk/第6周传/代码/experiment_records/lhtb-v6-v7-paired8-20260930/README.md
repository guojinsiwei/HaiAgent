# 本轮实验唯一入口：v6 对 v7，各 8 题

这是一次实验，不是新的算法版本。两组使用同样的八道题，共十六次正式运行。
任务与预算见 [PROTOCOL.md](PROTOCOL.md)。v6/v7 的源发布均保持不变。

- `arms/v6` / `arms/v7`：云端封存的两组源码，不在此继续开发。
- `manifest.json` / `jobs` / `ready.json`：题目、作业配置、封存哈希。
- `health.json`：正式实验总进度；没有此文件表示尚未启动正式实验。
- `summary.json`：已完成 trial 的分组、分数、异常与机制计数。
- `runs/v6-*` / `runs/v7-*`：官方结果和原始轨迹；`ledger` 防止重复启动。
- `checks-status.json`：无费用准备/验收状态；不是正式实验进度。

云端：`/var/tmp/lizh639-lhtb-v6-v7-paired8-20260930`。

## 隐藏输入启动

就绪后在 PowerShell 运行（仅本次进程允许执行该脚本，不修改系统策略）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\54177\Documents\ChatGPT\mcts\experiment_records\lhtb-v6-v7-paired8-20260930\Start-Paired8.ps1"
```

按提示输入模型密钥；不要发送到聊天。脚本先验证封存配置，已启动时拒绝重复运行。
若提示启动未确认，先检查状态，不要另建一份试验重跑。后台守护启动确认后可以关闭本地终端。
