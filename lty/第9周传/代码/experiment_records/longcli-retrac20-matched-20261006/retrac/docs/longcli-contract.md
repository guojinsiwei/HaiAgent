# LongCLI-Bench 接口与交接说明

本项目接入的是 [finyorko/longcli-bench](https://github.com/finyorko/longcli-bench)，不是 LongBench、LongCodeBench 或 Harbor。本次交付没有运行真实模型请求或 LongCLI-Bench 实验；离线测试不代表任务通过率。

## 核对版本与接口

核对的官方提交为 `2015f37b5c458f2562354de6b415e9182c91af64`。适配器通过 `--agent-import-path retrac.longcli:RetracAgent` 加载，不修改上游注册表。不能同时传 `--agent`。

- [BaseAgent](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/agents/base_agent.py)：实现 `name()` 和 `perform_task(instruction, session, logging_dir=None)`，返回原生 `AgentResult`。
- [AgentFactory](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/agents/agent_factory.py)：支持 `module:class` 导入路径并检查 `BaseAgent` 子类。
- [CLI](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/cli/tb/runs.py)：`--model` 转为 `model_name`，`--agent-kwarg key=value` 推断基本类型；自动注入的 `no_rebuild` 参数被适配器接收。拼错的其他配置名会立即报错。
- [TmuxSession](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/terminal/tmux_session.py)：使用 `send_keys(keystrokes, block=False, min_timeout_sec=duration)` 和 `get_incremental_output()`；保留换行、heredoc、`C-c` 与空按键轮询语义。模型命令仅发送到基准任务容器。

`vendor-contracts/` 只保留未经修改的上游 `BaseAgent`、`AgentResult`、`FailureMode` 定义、许可证和包含 SHA-256 的来源清单。离线测试加载这些真实定义，并模拟 tmux 与模板依赖；没有启动 Docker。

## 接手者准备环境

官方要求 Python 3.12+、Docker、Docker Compose 和 uv。建议使用 Linux 或已配置 Docker 的 WSL2 环境，在同一个 Python 环境中安装本项目和**官方 LongCLI-Bench 仓库**。仅安装 PyPI 的同名 `terminal-bench` 不能保证具备 LongCLI 的评分扩展。

以下为交接命令示例，本次未执行：

```bash
git clone https://github.com/finyorko/longcli-bench.git
cd longcli-bench
git checkout 2015f37b5c458f2562354de6b415e9182c91af64
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uv pip install -e /absolute/path/to/retrac

cd longcli_dockerImage
docker build -f Dockerfile.make-pytest-base -t tb/make-pytest:v0 .
docker build -f Dockerfile.c-env-base -t tb/c-env:v0 .
cd ..
```

任务数据、任务 Dockerfile、测试与评分脚本来自该仓库的 `tasks_long_cli/`；示例任务位于 `tasks_long_cli_example/`。适配器不复制隐藏测试，也不自行计算官方成功率。

## 配置与调用

```bash
export DEEPSEEK_API_KEY='YOUR_KEY'
export DEEPSEEK_MODEL='YOUR_PROVIDER_MODEL_ID'
# 官方 DeepSeek 默认地址为 https://api.deepseek.com。
# 兼容代理可设置 DEEPSEEK_BASE_URL 或传 --agent-kwarg base_url=URL。

tb run \
  --agent-import-path retrac.longcli:RetracAgent \
  --model "$DEEPSEEK_MODEL" \
  --dataset-path ./tasks_long_cli \
  --task-id 61810_cow \
  --output-path ./runs_retrac \
  --run-id retrac-deepseek-example \
  --n-attempts 1 \
  --give-test-output 1 \
  --n-concurrent 1 \
  --agent-kwarg rounds=8 \
  --agent-kwarg max_total_seconds=3600 \
  --global-agent-timeout-sec 3900
```

`--output-path` 和 `--run-id` 分别控制输出根目录和运行名称。所有 `RetracConfig` 与 `ModelConfig` 配置字段均可通过重复的 `--agent-kwarg` 设置，包含 `extra_body` JSON 对象；密钥只通过环境变量读取，不作为 CLI 字面值传入。模型名称由接手者根据账号可用模型填写。

三个层次的次数必须区分：

| 参数 | 含义 |
|---|---|
| `--agent-kwarg rounds=8` | 一次代理执行内的 RE-TRAC 轨迹轮数，轨迹之间重置对话并合并压缩记忆，任务容器状态保留。 |
| `--give-test-output 1` | 一次基准 attempt 的评测总轮数，1 表示没有额外测试反馈修复轮。设为 3 会最多执行 3 轮代理与官方测试，后两轮提供之前测试反馈。 |
| `--n-attempts 3` | 3 次独立 attempt，用于官方多次尝试统计，不等于内部轨迹轮数。 |

官方 [harness](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/harness/harness.py) 在每个测试反馈轮重新创建代理。适配器不把一个反馈轮的内部状态自动带入下一个反馈轮；上游负责提供原始任务与测试反馈，容器内文件延续。

内部预算 `max_total_seconds` 约束 RE-TRAC 执行。上游 `--global-agent-timeout-sec` 应留出更大余量，因为它还覆盖适配器启动和记录开销；上游在线程中运行代理，外部超时本身不保证立即取消正在运行的 Python 线程。不要依赖外部超时代替内部预算。

## 日志、评分与故障

每次 `perform_task` 写入 `<logging_dir>/retrac/<唯一ID>/`，包括 `events.jsonl` 和 `result.json`；逐轮状态包含在对应事件与结果文件内。同一基准反馈轮目录不会覆盖前一轮的 RE-TRAC 日志。密钥环境变量对应的值会交给日志脱敏器。

`AgentResult` 返回本次执行全部轨迹与压缩调用的输入、输出 token 数。上游对多次测试反馈轮的顶层 token 字段存在覆盖行为；做跨反馈轮成本统计时，应汇总每个唯一目录的 `result.json`，不能只读最终顶层值。

| 代理结束原因 | 原生 FailureMode |
|---|---|
| `protocol_error` | `FATAL_LLM_PARSE_ERROR` |
| `max_total_seconds_reached` | `AGENT_TIMEOUT` |
| 模型、终端、压缩等执行错误 | `UNKNOWN_AGENT_ERROR` |
| 正常返回或其他计算预算耗尽 | `NONE` |

`NONE` 只代表代理执行没有上述错误，**不表示任务成功**。F2P、P2P、组合通过率和步骤分数均由官方测试与 `scripts_python/longcli_aggregate_results.py` 产生。基准代码为 Apache-2.0；任务目录可能包含额外第三方许可证，应以对应目录为准。
