DSH + KZ repair5 三题小测（2026-10-13）
===================================
仅跑当前修复候选 KZ 0.2.6：hog → cats / ap35 两并发。
沿用上一轮 longcli-kz-dsh3-20261012 的冻结题目、镜像、starter、官方评分及预算。
TaoToken TokenPlan / deepseek-flash，thinking关闭，temperature=0。
每题800共享请求、600工具（包括元数据）、7200秒、100万上下文、32768输出。
压缩原生temperature不指定；50元/题保护为历史2/8费率估计，不是TokenPlan实际扣费。

变更：上一轮0.2.4升级为0.2.6，包含repair4+repair5修复；明确INSTRUCTION.md
作为各角色共用题面，开启已验收的Bash阶段退出码采集。回溯仍冻结。
主要观察：记忆生成/采纳/动作归因、子目标定义/验收/推进、拒绝时监控是否可达、
管道失败是否误判成功，以及原生DSH执行/压缩是否正常。得分不是唯一验收指标。
cats 的原始P2P有缺文件缺陷；仍报告未篡改的官方得分和success，不混成全通过。

原记录不覆盖；每题全新容器/home/工作区/记忆，只共享只读依赖。
首题工程故障则不派发后两题；正常低分照常继续。无自动付费重试。
全部进程及API代理在学院服务器脱离SSH运行，电脑关机不影响已确认启动的实验。
不启动GPT定时巡检、不发邮件。密钥仅本地隐藏输入→SSH stdin→服务进程内存，
不写参数、源码、密钥文件或日志。不复用旧实验密钥。

服务器：/var/tmp/lizh639-longcli-kz-dsh3-repair5-20261013
本地启动：powershell.exe -NoProfile -ExecutionPolicy Bypass -File Start-Repair5.ps1
验收通过后才允许输入密钥启动；ready.json为无API预检结果。
