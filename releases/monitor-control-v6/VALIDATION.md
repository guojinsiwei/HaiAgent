# v6 验收记录（2026-09-30）

## 结果

- 最终源码离线回归：**336/336 通过**。HAI 123、Lean 38、提示视图 20、适配器 32、
  修复与语义测试 105、结果分类 7、监督器 11；模型 API 调用为 0。
- 旧 12 题日志只读回放：**465/465 触发点输入构建通过**，每次至少 8 条证据。
  MATPOWER 为 **74/74**，最大 payload 15,400 字符；原先输入超限导致不可达的场景不再复现。
  模拟调度每题不超过 12 次调用，12/12 题均覆盖最后 10% 工具预算；MATPOWER 最后一次在第 550 步。
- 云端真实 Docker 完整兼容性验收：**29/29 通过**，没有外部模型调用、测试容器清理错误。
  之后又收紧小上下文降级和 trap 覆盖的保守判断；最终源码重新通过上述 336 项回归和 12 题回放，
  并复验全部 3 项新增 Docker 核心验收，**3/3 通过**。29 项结果与最终 3 项结果分开保存，
  不将前者冒充最终边界版本的完整重跑。
- 本地源码与最终云端 source manifest 全部匹配；HAI 的 21 个源码文件与 v5 完全一致。
  Docker suite 还校验原始冻结源码哈希；没有改旧 trial 或 reward。

## 三项核心 Docker 验收

1. 真实执行 `python ... raise RuntimeError ... | tail`：最终进程退出码仍为 0，
   可见管道阶段 `[1, 0]`，`suspected_failure=true`、`execution_clean=false`，
   `check_status=unknown`、`task_success=null`。
2. 连续读取相同结果触发恢复事件；脚本 Actor 给出修复计划后真实写入目标文件，
   随后单独运行验证命令。记录 1 次 `recovery_verified_repairs`，共 5 次工具执行。
3. 在真实 Docker 中读取最终文件并交付快照，确认产物为 `repaired`，不是模型口头声明。

补充单测覆盖未执行的自报、重复失败计划、目标没有实际修改、错误输出混杂成功标记、
忽略计划直到超时、最多两次补计划门控、非法目标路径、长任务/长恢复计划、非法可选记忆、
管道多阶段错误、主动处理错误、errexit/pipefail/$?、exec、超时和 trap 修改等。

## 证据文件

- [最终离线回归汇总](evidence/validation.json)，分组原始输出为 `evidence/regression-*.log`。
- [12 题回放](evidence/replay-12.json)：逐题原日志路径、SHA-256、输入长度、证据数量和模拟调度。
- [完整 Docker 兼容性验收](evidence/docker-full-before-final-boundaries.json)：
  云端 `run-20260930-204652-de9a729c`。
- [最终边界版本 Docker 核心复验](evidence/docker-final-boundaries.json)：
  云端 `run-20260930-205315-b6986fb8`。
- [最终源码清单](fixed-source-manifest.json)、[集成代码清单](integration-source-manifest.json)。

云端原始日志、执行轨迹和测试运行目录保留在 `/var/tmp/lizh639-monitor-control-v6`。
测试仅清理自己标记的临时容器/镜像，没有操作现有正式实验容器。

## 复现

在该云端发布目录、使用已安装的 Linux Python 环境执行：

```sh
python -B release_tools.py
python -B verify_release.py
python -B replay_monitor.py /var/tmp/lizh639-lhtb-bestfgs12-memory-v5-20260930
python -B cloud_suite.py
# 只验收新增 Docker 闭环：
INTEGRATION_CASES=monitor_control_v6_case python -B cloud_suite.py
```

`cloud_suite.py` 依赖该服务器现有 Docker、冻结基线和 Python 分发路径。
测试模型为脚本响应，Python 网络连接被禁用，测试容器使用隔离网络；不需要 API key。

## 尚未证明的事项

此次没有启动新的付费 12 题实验。离线回放不能证明真实 Monitor 会作出正确判断，
脚本闭环不能证明真实 Actor 会遵循计划或选出充分的验证标准。
下一轮真实实验应对比后段监控可达率、疑似/真实失败分类、恢复计划执行率、
修改后验证次数和干预前后重复率，以及最终任务得分；不能用记忆条数替代收益。
