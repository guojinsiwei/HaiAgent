# BestFGS 当前执行核心阅读包

本目录抽取的是当前 LongCLI 对照实验实际使用的 BestFGS v6.1，即 v6 算法加已有工程修复。
主入口是 `LeanTaskRunner`，不是旧的语义最佳优先图搜索。这个包用来独立阅读、离线测试，
以及在已隔离的 Linux 环境运行单个 CLI 任务；“有效单元”指依赖完整且可执行，不代表算法已证明有效。
原项目和正在运行的实验未修改。

## 先运行再阅读

需要 Python 3.11 或以上，无第三方 Python 包依赖。Windows 上先在这个目录执行：

```powershell
python demo.py
python run_checks.py
```

`demo.py` 用脚本化模型展示：已记录的失败记忆匹配到拟执行动作，控制器要求重新考虑，
随后模型换成另一动作。它不调用 API、不运行真实模型命令，也不是效果实验。
`run_checks.py` 运行原版行为和模型响应解析测试；Windows 会跳过 7 项 POSIX 执行器测试。

## 建议阅读顺序

| 顺序 | 文件或函数 | 需要弄清的问题 |
|---|---|---|
| 1 | `demo.py` | 环境、主模型、顾问、配置如何传给控制器？ |
| 2 | `src/bestfgs/lean_protocol.py` | 模型能提出哪些动作？配置和预算如何定义？ |
| 3 | `src/bestfgs/lean_runtime.py` 的 `run` | 每轮先做什么检查，在哪里决定执行、咨询、恢复和提交？ |
| 4 | 同文件的 `_ask`、`_panel`、`_record_turn` | 实际发送给模型的对话和固定上下文是什么？ |
| 5 | `lean_conversation.py`、`monitor_context.py` | 历史如何压缩和召回？监控为何有时看不到足够证据？ |
| 6 | `lean_memory.py`、`memory_events.py` | 什么信息能入库，依赖状态如何限制记忆适用性？ |
| 7 | `lean_runtime.py` 的 `_memory_push`、`_record_memory_reconsideration` | 记忆如何从展示变成一次重新决策，如何审计后续动作？ |
| 8 | `lean_monitor.py` | 监控何时调用模型，如何判断停滞、生成候选记忆？ |
| 9 | `stagnation_control.py` 的 `_control_before`、`_control_outcome`、`_fail_recovery` | 恢复计划是否被执行、是否换路，以及失败后发生什么？ |
| 10 | `tool_outcomes.py`、`shell_probe.py` | 命令退出成功、公开检查通过和任务成功如何区分？ |
| 11 | `lean_environment.py`、`environment.py` | 工具真正在哪里执行，工作区指纹和文件快照怎样计算？ |
| 12 | `retrac_adapter.py`、`model_wire.py`、`response_repair.py` | API 请求、JSON 解析、重试和格式修复怎样影响实验？ |

`models.py` 只保留需要的数据类型和相关定义。前十项最接近你现在关心的算法问题，
不要从传输、Docker 或历史图搜索文件开始读。

## 一轮真实决策经过哪里

```text
run_task.py 或实验中的 runner.py
  → LeanTaskRunner.run
      → _maybe_monitor               必要时进行语义监控
      → _consult                     必要时询问顾问
      → _ask → _panel                组织上下文并获取主模型动作
      → parse_action                 校验动作格式
      → _control_before              检查恢复计划要求
      → _record_memory_reconsideration / _memory_push
                                     检查记忆是否要求重新决策
      → _run_command → environment.execute
                                     执行命令
      → assess / _control_outcome     收集结果并推进或失败恢复计划
      → 更新证据、对话、记忆和预算
      → 下一轮，直到提交、预算耗尽或错误停止
```

这是顺序执行控制器，有 checkpoint 和 restore 动作，但不等于每一步都做图搜索。
Actor、advisor、monitor 是三个独立客户端，当前实验使用同一种 DeepSeek 模型，
不是三个不同模型。RAW 只有顺序动作客户端。

## 和当前实验有关的待解决问题

2026 年 10 月 1 日约 16:39 的 Scheme 首题日志显示：v6 运行约 48 分钟，
已调用 536 次工具；最近 50 次调用约 8 分钟没有工作区文件变化，
累计 60 次恢复计划和 57 次恢复失败，没有记录到验证通过的有效修复。
这些数字是当时的检查快照，不是最终成绩；文件没有变化本身也不能证明诊断无价值。
结合反复解析同一批测试输出、重复对齐预期与实际结果的轨迹，才构成停滞证据。

重点检查 `stagnation_control.py`：失败后有没有强制形成真正不同的假设和行动，
还是只再次向模型提供一段“换一种方法”的文字。再检查 `_panel` 和对话压缩：
哪些失败证据、历史计划及记忆真正进入了下一次请求。不要用记忆条数或恢复次数代替有效换路。

RAW 的首题当时仅运行约 7 秒、调用两次工具，因三次格式错误结束，
模型输出混入 DSML 标记而非纯 JSON。这个异常属于输出协议问题，
不能解释成 RAW 已快速解题或其解题能力必然更差。

## RAW 对照代码

`src/haiagent/runtime.py` 的 `run` 配合 `Config(method='raw', response_protocol='json')`
就是当前实验的 RAW 路径。该文件复用 HAI 通用代码，因此还含有其他模式的分支；
RAW 模式不启用 BestFGS 的记忆干预、顾问、监控或分支恢复。
`src/terminal_context` 是它需要的基础上下文依赖，不是另一个解题模型。

## 运行一个真实本地任务

只在可丢弃、已隔离的 Linux 或 WSL 环境使用。执行器会运行任意模型命令，
目录检查不构成安全沙箱；不要把它直接指向个人文件或有凭据的工作环境。
运行前在环境变量设置 `DEEPSEEK_API_KEY`，不要把密钥写进源码或命令参数。

```bash
python run_task.py --seed /tmp/task-seed --goal-file /tmp/task-goal.txt \
  --out /tmp/new-bestfgs-run --allow-local-execution
```

`--out` 必须是尚不存在、且不在 seed 内的目录。默认同模型三客户端、
600 工具、800 模型请求、2 小时上限，开启自动记忆、语义监控、结果可信度和停滞恢复。
实际结果仍需要独立检查，本脚本不提供官方 LongCLI 评分。

## 实验适配层和抽取边界

`experiment_adapter` 保留当前 LongCLI 的六个真实适配文件原文，仅用于理解：
`runner.py` 如何选择 v6 与 RAW、记录各角色请求；`environment.py` 如何把命令送入隔离环境；
以及 `audit.py`、`net_transport.py`、`common.py`、`chroot_entry.py` 的作用。
该层没有带官方镜像、任务、协议文件、服务器路径配置或测评器，不能直接启动完整 benchmark。
需要先读 `run_task.py`，再用这层核对实验和单任务执行环境的区别。

没有复制整个历史仓库、旧搜索调度器、训练代码、云端部署队列、任务数据、实验日志、
密钥或缓存。LHTB 五组实验基于 v7 并增加候选路线控制，不与这个 v6 阅读包混放。

主循环、记忆、监控、恢复和 RAW 运行文件均原样复制。少数依赖模块按静态引用关系
移除未使用的顶层定义，保留的函数和类不改写；包初始化移除旧图搜索的自动导入。
新增单任务入口和离线示例是阅读工具，并非原实验入口的替代声明。
`SOURCE_MANIFEST.json` 记录原文件、SHA256 和保留定义的原始行号；
`verify_sources.py` 校验提取后的文件和定义。`VERIFICATION.json` 记录本包的验收结果。
