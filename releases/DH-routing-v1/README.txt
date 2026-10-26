DH-routing-v1，基于 DH-subgoal-v1 的异常处理对照候选。
三组均使用独立子目标、依赖图和实际检查证据。
13：局部修正 + 只读侦查；134：增加完成验收；1342：增加检查点回溯。
实际开关为 bestfgs.error_routing.RoutingPolicy，运行器 RoutedTaskRunner。
Critic仍使用同一deepseek-flash，每轮先规划公开检查，执行后再次审核实际输出。
所有新增调用计入原预算。最多2轮验收、2次回溯、3次局部修正。
回溯仅在相同固定检查曾通过、工作区变化并出现两次真实失败后触发；恢复前保留当前文件。
原正交门控、重复命令拦截仍保留。所有局部通过均不等于官方成功。
对应部署与具体协议见 experiment_records/longcli-dh-routing3x7-20261008。
本release包含旧验收证据作为历史参考，本轮验收以对应实验目录ready.json为准。
