# BestFGS 监控与行动闭环 v6

基于 `memory-reliability-v5` 的独立发布，修复监控可达性、工具结果反馈和停滞后行动闭环。
旧实验、旧发布、旧评分不被覆盖；HAI 的 21 个 Python 源文件保持不变。

## 三项改动

1. **监控可达性**：任务只保留一份有哈希和省略标记的摘要，去掉 delivery 中重复正文。
   默认带最近 8 条执行证据，最多补 2 条历史关键事件；按实际 JSON 长度逐级精简。
   极小预算下减少到最近 4/2 条证据，不直接丢弃整次监控。Actor 仍持有原任务。
   默认 12 次配额分为 6 次全程周期检查和 6 次逐渐释放的异常检查，后者不能挪用前者。
   `monitor_context_built` 记录大小/模式/证据数量；`monitor_deferred` 区分输入构建、
   模型请求、结果校验失败，模型异常另有 `model_error` 记录。非法可选记忆不再吞掉有效监控结论。
2. **工具结果可信度**：对顶层 `bash -c/-lc` 通过独立描述符记录管道各阶段退出码，
   不强行开启 pipefail，不改变原命令退出码。进程成功、疑似异常、公开检查通过分别表示。
   `python ... | tail` 即使最终退出 0，前段失败也会成为警告，不再给记忆/失败检测发干净成功信号。
   明确的直接 pytest 通过摘要才标为 `public_check_passed`；普通读取、echo 和无错误码不等于检查通过。
3. **停滞后的行动闭环**：语义监控判为停滞，或同命令/状态/输出至少重复 3 次时，
   建立恢复事件，要求 Actor 提出假设、目标文件、具体动作、独立验证命令和预期观察。
   命令仍由 Actor 决定并正常执行；计划本身不会触发工具。系统跟踪是否执行、是否实际改变目标、
   是否随后执行验证、结果是否满足约定。8 次工具内没完成或验证失败就重新选路；
   同一工作区中失败的计划不能仅改假设措辞再次通过。最多两次请求补充计划，不无限卡住执行。

## 评价口径与边界

- `recovery_verified_repairs` 只表示指定目标确有修改且计划中的公开检查通过，**不是任务成功率**。
  `recovery_checked_hypotheses` 单列诊断性检查，不计作修复；模型自报“已经执行/修好了”不算。
- 非零管道阶段可能是 grep 无匹配、head 导致 SIGPIPE、或主动处理错误。它是待复核警告，
  不是因果判断、行动禁令或整个任务失败。
- Bash 观测仅覆盖顶层。嵌套 shell、其他 shell、Python 捕获异常等不能保证完全可见。
  trap 修改、exec 绕过退出观测、超时、超过 128 条状态记录会保守标为不完整。
  文本含 trap 也可能触发保守降级；这是可观测性限制，不是任务错误。
- 验证标准仍由模型提出，不能排除弱检查；未引入隐藏评分、自动图搜索或未经验证的跨任务规则。
- 12 题旧日志回放只验证输入大小和调度覆盖；不执行旧命令、不重造旧管道状态，
  不宣称旧模型本来会作出新判断，更不能据此声称分数提高或真实循环减少。

## 使用和消融

本发布 CLI 与 `integration/transport.py` 默认开启三个新开关，同时继承语义监控和自动记忆。
底层 `LeanConfig()` 为兼容旧集成默认关闭；直接构造时须显式设置
`monitor_reliability=True, outcome_reliability=True, stagnation_control=True`。
语义监控仍需独立 monitor_client；没有增加一个新的决策模型角色。

CLI 可用 `--no-monitor-reliability`、`--no-outcome-reliability`、`--no-stagnation-control` 分别消融。
监控可靠性开启时周期调度取代旧固定 interval，仍保留 cooldown 和总调用限额。

```sh
PYTHONPATH=sources/bestfgs-project/src python -m bestfgs.lean_cli \
  --workspace /path/to/disposable-task --run-root /path/to/new-run \
  --model MODEL_ID --goal '任务要求'
```

云端独立发布目录：`/var/tmp/lizh639-monitor-control-v6`。上传不代表启动新正式实验。
验收结果和复现方法见 [VALIDATION.md](VALIDATION.md)。
