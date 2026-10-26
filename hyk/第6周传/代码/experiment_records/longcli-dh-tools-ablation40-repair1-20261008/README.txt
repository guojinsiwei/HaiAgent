两组各20题，全新轮次，不复用旧成绩，不跨题记忆。
dh_1234_tools：子目标＋局部修正、侦查、Critic、回溯＋inspect_code/edit_code/verify_goal。
dh_1234_no_tools：相同子目标＋1234，不提供上述三个工具，仍可普通run执行CLI命令。
同一冻结源码；两组共用执行修复、ANSI清洗、记忆、监控器、向导和字节上下文保护。
deepseek-flash，thinking off，temperature 0；每题800实际API尝试、600工具、7200秒。
4096输出tokens、48000字节最终messages输入硬上限。所有角色与重试共用预算。
统一学院Docker，每题2CPU/8GiB；两组CPU绑定互不重叠；总并发12，每组最多6。
每题全新工作区、home、tmp、容器；网络禁用、官方隐藏测试不暴露给Solver。
官方评分单独运行，结果不回注Solver。邮件关闭，零GPT定时任务。
原轮次与原始日志完整保留并标记退役；新轮次必须重新通过免API验收。
远端：/mnt/sdb/home/lizh639/longcli-dh-tools-ablation40-repair1-20261008。
修复：有/无工具共用实际最终上下文裁剪；接受cwd为.和同一goal_id的verify元数据。
验收必须通过两组完整长轨迹请求链和失败现场上下文回放。
首题出现工程错误不展开；同组连续两题同类工程错误立即停止调度及付费任务并保留现场。
密钥只经本地隐藏输入和SSH标准输入传递，不写参数、环境、文件或日志。
