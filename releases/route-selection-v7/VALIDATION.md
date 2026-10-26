# v7 验收与对照保全（2026-09-30）

## 已通过

- 最终离线回归 **368/368**，包含新增路线选择测试 **32 项**，模型 API 调用为 0。
  分组：HAI 123、Lean 38、提示视图 20、适配器 32、修复/语义/路线 137、分类 7、监督器 11。
- 云端真实 Docker **38/38**，包含 9 项新增路线验收，模型 API 调用为 0，测试资源清理错误为 0。
  Docker 验收使用的 **131 个算法/执行源码文件与最终发布哈希一致**。
  收尾只更正了适配器的旧 v5 发布标签，并重跑上述最终离线回归；不是修改算法后沿用旧验收。
- 对照保全：v6 的 **130 个源码文件、5 个集成文件**全部保持原哈希；v6/v7 共有
  `LeanConfig` 默认值没有变化；HAI **21 个源码文件**完全一致。

## 真实 Docker 中验证了什么

1. **恢复较早候选**：A、B 都通过相同检查，A 的步骤更少。实际试完 B 后，恢复 A 的快照，
   最终文件内容为 `good A`，不是留在最后试过的 B。
2. **无收益回退**：两条路线都未通过同一检查，恢复共同起点；真实最终文件为缺失，
   与实验前一致，没有把失败候选当作进步留下。
3. **证据决定预算投向**：探针得到预注册的 B 支持/A 反驳观察，只试 B，最终文件为 `good B`。

每个场景同时核对选择结果、共同起始工作区、真实文件恢复、实际工具成本和模型请求数。
两路试做产生独立文件状态，所有内部工具进入原有总工具计数，不额外请求脚本 Actor。

新增离线测试还覆盖：未知/矛盾/失败探针、基线已经通过、检查缺失失败标记、
检查或探针偷偷修改工作区、模型自报成功、通过检查但目标未变、两个候选互不继承文件、
缺计划时的有限门控、工具/时间/模型预算不足、试探中断恢复、保留已验证候选、
同条件失败记忆直接淘汰重复候选、新观察重新开放旧路线、非法路径和无区别候选等。

## 可核查记录

- [离线回归汇总](evidence/validation.json)，原始分组输出为 `evidence/regression-*.log`。
- [Docker 验收结果](evidence/docker-acceptance.json)。
- [对照版本及共同默认值核验](evidence/control-preservation.json)。
- [最终源码哈希](fixed-source-manifest.json)、[最终集成哈希](integration-source-manifest.json)。
- [冻结 v6 源码清单](control-source-manifest.json)、[冻结 v6 集成清单](control-integration-manifest.json)。

云端完整 Docker 日志和轨迹目录：
`/var/tmp/lizh639-route-selection-v7/run-20260930-211810-5c0d4617`。
其中各路线案例的 `method/events.jsonl`、`graph.json`、`route-memory.json` 和文件快照可用于审计。

## 复现与下一轮实验

在服务器新发布目录使用既有 Linux Python 环境执行：

```sh
python -B release_tools.py
python -B verify_release.py
python -B check_control.py /var/tmp/lizh639-monitor-control-v6
python -B cloud_suite.py
# 仅运行新的三场景/九项真实 Docker 检查：
INTEGRATION_CASES=route_selection_v7_case python -B cloud_suite.py
```

Docker 验收依赖该服务器现有冻结基线和 Python 分发路径；测试容器无网络，
脚本模型不发送外部 HTTP 请求，也不需要模型凭据。

此次**没有启动付费对比实验**。[comparison-plan.json](comparison-plan.json) 是对照准备配置，
不是已启动或已封存的实验。正式运行前仍需生成两个独立作业集、匹配任务/镜像/模型参数并封存。
应同时重跑 v6/v7，保持逐题预算一致，交错执行顺序，记录官方得分和全部成本。

本次验收证明控制器按约定完成试探、选择和恢复，不证明真实 LLM 能提出有效的竞争假设或
充分的公开检查，更不证明真实任务得分优于 v6。下一轮正是验证这两件事，而不是比较记忆数量。
