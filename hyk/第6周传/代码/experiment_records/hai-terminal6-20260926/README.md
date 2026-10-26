# HAIAgent / Raw Terminal-Bench 六题配对试验

学院节点 `lizh639@172.16.108.236`，独立目录 `/mnt/sdb/home/lizh639/hai-terminal6-20260926`。
复用旧项目的固定镜像、Harbor 运行时和仅在评测阶段注入的离线 verifier 依赖，不修改旧题单/代码/结果。

- HAIAgent 0.2.0 与同工程 Raw，各 6 题，共 12 次。
- 从此前排除了冻结测试集的 36 道开发题中，按题号排序后使用种子 20260926 洗牌取前 6 个，不按结果筛选。
- 模型沿用 `deepseek-flash`，API 为 `https://api.deepseek.com`；模型不可用即停止，不私自换模型。
- 原题公开时间限额作为策略实际墙钟上限；外围额外预留 120 秒，仅供启动/结束，不追加决策预算。
- 共用 80 决策轮、70 工具调用、每次最多 4096 输出 token、相同采样与请求预算；不是相同总 token 消耗实验。
- 单容器串行、方法先后交替；每次独立容器；40 GiB 余量保护；无整题自动重跑。
- API/基础设施/官方评测异常暂停；模型正常预算耗尽仍评测最终环境。任务失败不自动重试。
- 成功来自官方 verifier，不来自模型自评。交互轮次来自 Agent trace。语境冗余率离线审计，未审核为 null。
- 官方 Harbor 结果与 run/task/artifact/trace 哈希绑定在 `harbor-evaluation.json`；本部署的 report 汇总读取真实报告。
- 这是开发试验，不当作隐藏测试集成绩，不能凭六题宣称显著提升。

预检先运行全部 Linux 回归测试，再在两份独立任务容器中使用脚本策略执行一次命令、提交并调用原版官方 verifier。预检不调用模型、不尝试解决题目，不能作为算法成绩。

启动：本机 PowerShell 执行 `Start-HAIPilot.ps1`，密钥隐藏输入，通过 SSH stdin 交接到云端 owner-only `/dev/shm` 文件；worker 读取后立即删除交接文件，不写入配置或日志。宿主/容器内存仍需可信，不能承诺抵抗拥有 Docker/root 权限的其它用户。

tmux socket `hai-terminal6`，session `paired6`。本机关机不影响云端运行；本次不建立 GPT 周期巡检。服务器重启、磁盘保护或真实故障会暂停，不承诺永久在线。
