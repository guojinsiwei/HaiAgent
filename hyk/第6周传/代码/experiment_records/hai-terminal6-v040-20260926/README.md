# HAIAgent 0.4.0 Terminal-Bench 配对重启

云端：lizh639@172.16.108.236:/mnt/sdb/home/lizh639/hai-terminal6-v040-20260926。

固定原 6 题，HAI/Raw 各 6 次，串行交替顺序；同一模型 deepseek-flash、thinking=disabled、原生工具调用、相同环境/官方 verifier/预算。新实验不混合 0.2.0、0.3.0 数据。

新 HAI 方法由自动重复观察记忆、决策提示、重复理由检查组成；不能将联合效果单独归因于记忆。相同输出计数不是论文工具调用冗余率。所有拒绝执行的模型决策仍计交互轮次，不计工具执行，无额外 API 修复调用。模型仍可随时提交。

旧 0.3.0 于完成 5 次运行、执行第 6 次时按用户要求停止；日志、结果与中断环境保留。新一轮全部从干净任务环境运行。

真实日志离线回放在工具调用 19 检出第 3 次相同输出并生成 M1；该验证不执行命令、不调用模型、不声称反事实成功。

Start-HAIPilot.ps1 会先验证 ready.json，再提示隐藏输入 Key，通过 SSH stdin 传入远端私有 /dev/shm 临时目录；worker 读取即删除。看到 launched=true 后是 tmux 离线运行，关机不终止云端 worker。节点故障仍可中断，不承诺永久在线。无 Codex 周期巡检。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\54177\Documents\ChatGPT\mcts\experiment_records\hai-terminal6-v040-20260926\Start-HAIPilot.ps1"
```

不重用旧启动脚本，不自动恢复旧实验，已经有 health.json 时拒绝重复启动。启动失败先查状态，不盲目重试。
