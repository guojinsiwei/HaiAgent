# BestFGS 语义循环判断与事件记忆 v4

在 `model-output-repair-v3` 工程基线上新增两个可独立消融的机制。不修改历史实验、
HAI 决策源码或官方评分，不启用自动分支恢复，不额外增加 800 轮 / 600 工具总预算。

## 默认模型选择

Actor 解题、Monitor 判断轨迹与提炼记忆、Advisor 提出替代假设：三个职责，
Monitor 默认沿用解题模型的型号和连接配置，但使用独立实例、独立短上下文。
不继承 Actor 对话，也不直接执行工具。可显式指定更便宜的小模型和独立服务商。

先使用同模型独立调用以验证机制，再单独比较小模型版本；本版本未证明任何型号的
准确率或性价比，也未发起真实模型六题重测。自动记忆与监控共享一次调用，避免重复审阅轨迹。

## 决策路径

执行结果 → 程序提出审阅触发 → Monitor 语义复核 → Actor/Advisor 继续。

- 默认每 24 次工具调用定期检查；冷却至少 8 次。失败聚集、工作区不变、公开检查完成、
  检查点创建和恢复等事件也可触发。程序只提出线索，工作区不变不等于停滞。
- 最近最多 16 条证据；输入总字符预算 20000（含系统指令和 1024 字符修复预留），
  输出最多 1536 token；每题最多 12 次 Monitor 调用，单次请求一次尝试、45 秒上限。
  所有调用计入任务总轮次/时间，保留最后一个 Actor 轮次，不额外补偿预算。
- Monitor 输出 progress / necessary_retry / stalled / uncertain，附具体证据和下一项检查。
  stalled 至少引用两步且提供检查；它触发既有 Advisor，受原有容量/冷却约束。
  progress / necessary_retry 可以撤销同一轮程序启发式触发的建议请求。
- 判断仍是模型意见：不能终止、封禁动作或自动恢复。Actor 可不采纳；后续工具结果按 review ID
  记录，不把“换了命令”“文件改变”当作有效进展或因果收益。
- 超长上下文、无效 JSON/协议和模型服务失败会留下告警并继续 Actor；Monitor 凭据错误会
  禁用 Monitor。Actor/Advisor 的凭据错误仍保留原有终止规则。辅助失败不伪装成零错误。

## 自动记忆

仅任务内失败教训（blocker）和经过检查的步骤（procedure），每次最多两条候选。
必须有结论、条件、1–3 个当前窗口证据 ID，且每个 ID 至少有一段真实 stdout/stderr 原文支持。
程序检查引用/原文、类型、路径、证据所属工作区，拒绝过期工作区证据、伪造引用和越界路径；
同一工作区下相同结论/条件/目标去重。容量仍为 24 条，复用已有条件化检索和重复动作提醒。

“原文存在”不证明推断成立。自动记录始终标注 `evidence_quoted_model_claim_not_verified`，
保留来源、原文和 review ID，不升级为已验证事实。依赖文件改变时标为历史、需复查；
外部状态始终未验证。由于未保存每个历史文件的完整依赖版本，首版保守拒绝来自不同工作区
指纹的自动候选，不强行迁移旧结论。暂不跨任务共享，也不做语义冲突的自动覆盖裁决。

审计链：`auto_memory_candidate` → `memory_admitted` / `auto_memory_rejected` / duplicate →
下一次 `model_request` 的可见记忆 → 既有 `memory_intervention` / followup。
调用次数、入库数、曝光和行为变化都不是收益证明。

## 启用和消融

本发布的 CLI、Harbor 覆盖适配器默认两项开启。底层 `LeanConfig()` 为兼容旧行为仍默认关闭；
代码调用须显式设 `semantic_monitor=True, auto_memory=True` 并传独立 `monitor_client`。

CLI 示例（在一次性 Linux 工作区运行，MODEL_ID 由实际部署显式替换）：

```sh
PYTHONPATH=sources/bestfgs-project/src python -m bestfgs.lean_cli \
  --workspace /path/to/disposable-task --run-root /path/to/new-run \
  --model MODEL_ID --goal '任务要求'
```

- 关闭循环判断：`--no-semantic-monitor`。
- 关闭自动记忆：`--no-auto-memory`（不禁用原有 Actor 主动记忆，专门消融自动生成）。
- 两者均关闭：回到 v3 决策路径，保留审计限时修正和版本标识。
- 同服务小模型：`--monitor-model SMALL_MODEL_ID`。
- 独立服务：同时提供 `--monitor-model`、`--monitor-provider`、`--monitor-base-url`、
  `--monitor-api-key-env MONITOR_API_KEY`，只提供环境变量名，不把密钥写进命令。
- 调用限制：`--monitor-calls`、`--monitor-interval-tools`、`--monitor-cooldown-tools`。

Harbor 的 `integration/transport.py` 接受对应 snake_case 初始化参数：`semantic_monitor`、
`auto_memory`、`monitor_model`、`monitor_provider`、`monitor_base_url`、`monitor_api_key_env`。
创建新的实验目录时，sources 内源码和 integration 覆盖文件必须一起使用并封存哈希。
这个目录是独立发布与验收目录，不是已经启动的正式评测队列。

## 验证

`verify_release.py` 保存完整回归日志到 evidence；`cloud_suite.py` 在真实 Docker 中执行，
HTTP 响应由确定性测试替身提供，禁止外部模型网络请求。最终结果见 `VALIDATION.md`。

后续比较先固定解题模型与总预算，测试两开关的四种组合；再比较 Monitor 同型号与小模型。
离线标注评估误报/漏报，在线评估得分、工具调用和费用。现有六题属于开发集，不能同时
用来调规则又宣称泛化收益。当前实现不意味着停滞识别准确率或正式任务成绩已经提高。
