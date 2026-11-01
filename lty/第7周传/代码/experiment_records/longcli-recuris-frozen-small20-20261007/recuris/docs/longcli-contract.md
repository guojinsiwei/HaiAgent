# LongCLI-Bench 原生接口与交接

核对提交为 `2015f37b5c458f2562354de6b415e9182c91af64`，目标是 [finyorko/longcli-bench](https://github.com/finyorko/longcli-bench/tree/2015f37b5c458f2562354de6b415e9182c91af64)，不是 Harbor 或 LongBench。TTA 运行器会检查 checkout 的 HEAD；单次直接 `tb run` 由运行者保证版本。

## 调用协议

- [BaseAgent](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/agents/base_agent.py)：继承并实现 `name()`、`perform_task(instruction,session,logging_dir=None)`，返回原生 `AgentResult`。
- [AgentFactory](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/agents/agent_factory.py)：`--agent-import-path recuris.longcli:RecurisAgent` 动态导入；不要再传 `--agent`。
- [CLI](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/cli/tb/runs.py)：`--model` 变成 `model_name`；接收上游自动传入的 `no_rebuild`；其余错误配置名立即报错。固定版本以 `split('=')` 解析 agent kwargs，值中不能再有等号。复杂配置应改用程序化 API。
- [TmuxSession](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/terminal/tmux_session.py)：`send_keys(keys,block=False,min_timeout_sec=...)` 后 `get_incremental_output()`。普通 execute 原样传按键，不自动加回车、拆 heredoc 或在宿主机执行。只有显式 verify 在容器终端中构造带回执标记的子 bash。

## 生命周期和输出

官方 [harness](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/harness/harness.py) 在代理返回后运行测试。`--give-test-output` 是官方评测总轮数，1 表示无额外测试反馈修复。多轮时容器延续但 agent 重建；不能把它作为论文独立重试。

TTA每次强制单任务、`--n-attempts 1 --give-test-output 1 --n-concurrent 1`，使用新run ID启动新的 `tb run`。单trial结果是：

```text
<output>/<run_id>/<task_id>/<task_id>.1-of-1.<run_id>/results.json
<output>/<run_id>/<task_id>/<task_id>.1-of-1.<run_id>/agent-logs/recuris/<uuid>/
```

aggregate `<output>/<run_id>/results.json` 不是 Meta 证据入口。`TrialResults` 定义见 [harness/models.py](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/harness/models.py)，路径见 [trial_handler.py](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/handlers/trial_handler.py)。

`is_resolved` 可能是 `null`。TTA要求准确的bool、匹配的task/trial、完整测试和trial结束时间、恰好一轮 LongCLI test turn，并检查错误类型；缺失或测试故障被标为 `incomplete`。正常运行可能保留 `failure_mode=unset`，所以它可接受；agent timeout若后续官方测试完整，也可形成合法结果。其他未知/解析/测试错误不会当作训练失败bit。

## 模型与预算

DeepSeek兼容示例见README。使用其他服务时明确指定端点和密钥变量，例如：

```bash
export OPENAI_API_KEY='YOUR_KEY'
export OPENAI_MODEL='YOUR_MODEL_ID'
export RECURIS_API_KEY_ENV=OPENAI_API_KEY
export RECURIS_BASE_URL=https://api.openai.com/v1
export RECURIS_MODEL="$OPENAI_MODEL"
bash /path/to/recuris/scripts/run_longcli.sh /path/to/longcli-bench TASK_ID

python -m recuris tta --benchmark-root /path/to/longcli-bench --task-id TASK_ID \
  --model "$OPENAI_MODEL" --api-key-env OPENAI_API_KEY --base-url https://api.openai.com/v1 \
  --memory /path/to/terminal-seed.json --output-dir /path/to/new-run
```

脚本用 `RECURIS_*` 变量；Python CLI通过命令行参数配置服务。底层地址优先显式 `base_url`，其次 `DEEPSEEK_BASE_URL`、`DEEPSEEK_API_BASE`、`OPENAI_BASE_URL`、`OPENAI_API_BASE`。更换供应商时显式传端点，避免残留环境变量生效。模型需兼容非流式 Chat Completions；本实现不自动改变模型或推理设置。

单次执行的所有角色共用内部时间和调用预算；Meta另有默认600秒、16次调用上限。TTA默认每attempt外层 agent 超时3900秒、整个 `tb run` 进程4500秒，须为官方测试留余量。网络socket超时、上游线程超时和 subprocess 超时都不等于严格取消容器内全部进程，严格截止由实验环境监管。中断/超时结果不能自动视为已完成评分。

| 内部停止 | AgentResult.failure_mode |
|---|---|
| JSON协议错误 | FATAL_LLM_PARSE_ERROR |
| 内部时间预算耗尽 | AGENT_TIMEOUT |
| 模型/终端/运行错误 | UNKNOWN_AGENT_ERROR |
| 完成、主动停止或其他预算耗尽 | NONE |

NONE表示未发生上述执行错误，不表示官方成功。官方 F2P/P2P 与步骤指标保留在基准结果中。跨反馈轮顶层 token 可能被后轮覆盖；本TTA固定一轮，并保留所有Actor/W/Meta的独立用量记录。

`vendor-contracts/` 是固定提交的接口类型和原始许可，仅供离线测试；基准本体和任务许可证仍以原仓库为准。
