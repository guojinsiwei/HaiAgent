# Reflexion × LongCLI-Bench 接口与交接说明

接入目标是 [finyorko/longcli-bench](https://github.com/finyorko/longcli-bench)，固定核对提交 `2015f37b5c458f2562354de6b415e9182c91af64`。本项目没有运行真实模型、Docker 任务或基准实验；离线测试只验证代码行为和接口兼容性。

## 原生接口

使用 `--agent-import-path reflexion.longcli:ReflexionAgent` 动态加载，不修改上游注册表，不能同时传 `--agent`。适配器继承真实 `BaseAgent`，实现 `name()` 和 `perform_task(instruction, session, logging_dir=None)`，返回原生 `AgentResult`。接口与导入检查见 [BaseAgent](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/agents/base_agent.py) 和 [AgentFactory](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/agents/agent_factory.py)。

模型终端行动只进入传入的任务 tmux 会话：`send_keys(keystrokes, block=False, min_timeout_sec=duration)` 后读取 `get_incremental_output()`。保留换行、heredoc、`C-c` 和空字符串轮询；不在运行适配器的宿主机执行模型命令，不包装成 `bash -c`。上游终端 API 见 [TmuxSession](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/terminal/tmux_session.py)。

`vendor-contracts/` 收录未修改的原生 `BaseAgent`、`AgentResult`、`FailureMode` 定义、Apache-2.0 许可证与 SHA-256 来源清单。离线测试加载这些真实定义，仅模拟 tmux 和模板依赖。它们不是整个基准的替代实现。

## 接手者安装环境

使用 Python 3.12+、Docker、Docker Compose 和 uv；推荐 Linux 或已配置 Docker 的 WSL2。在同一 Python 环境中安装**官方 LongCLI-Bench 仓库**和本项目。PyPI 上同名 `terminal-bench` 不保证包含 LongCLI 评分扩展。环境依据 [官方说明](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/README.md)。

以下均为交给实验执行者的命令，本次没有执行：

```bash
git clone https://github.com/finyorko/longcli-bench.git
cd longcli-bench
git checkout 2015f37b5c458f2562354de6b415e9182c91af64
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uv pip install -e /absolute/path/to/reflexion

cd longcli_dockerImage
docker build -f Dockerfile.make-pytest-base -t tb/make-pytest:v0 .
docker build -f Dockerfile.c-env-base -t tb/c-env:v0 .
cd ..
```

任务、Dockerfile 和官方测试由上游 `tasks_long_cli/` 提供；本项目没有复制任务、隐藏测试或评分实现。基准代码为 Apache-2.0，任务目录内第三方内容以各自许可证为准。

## DeepSeek 兼容配置

```bash
export DEEPSEEK_API_KEY='YOUR_KEY'
export DEEPSEEK_MODEL='YOUR_PROVIDER_MODEL_ID'
# 默认 https://api.deepseek.com；使用代理时再设置：
# export DEEPSEEK_BASE_URL='https://your-compatible-endpoint/v1'

bash /absolute/path/to/reflexion/scripts/run_longcli.sh \
  /absolute/path/to/longcli-bench 61810_cow \
  --output-path /absolute/path/to/runs_reflexion \
  --run-id reflexion-example
```

单任务参数必须是 `tasks_long_cli/` 中现有目录名；要运行全部任务，第二个参数显式填写 `--all`。脚本只组装 `tb run`，不安装软件、不下载数据。后续参数原样传入 `tb run`。脚本的 `REFLEXION_MAX_TRIALS`、`REFLEXION_MAX_SECONDS`、`REFLEXION_HARNESS_TIMEOUT` 分别默认为 3、3600、3900。

直接调用的等价示例：

```bash
tb run \
  --agent-import-path reflexion.longcli:ReflexionAgent \
  --model "$DEEPSEEK_MODEL" \
  --dataset-path /absolute/path/to/longcli-bench/tasks_long_cli \
  --task-id 61810_cow \
  --output-path /absolute/path/to/runs_reflexion \
  --run-id reflexion-example \
  --n-attempts 1 --give-test-output 1 --n-concurrent 1 \
  --agent-kwarg max_trials=3 \
  --agent-kwarg memory_size=3 \
  --agent-kwarg max_total_seconds=3600 \
  --global-agent-timeout-sec 3900
```

## OpenAI 或其他兼容端点

密钥环境变量与端点都由运行者明确选择，不能只改模型名：

```bash
export OPENAI_API_KEY='YOUR_KEY'
export OPENAI_MODEL='YOUR_PROVIDER_MODEL_ID'
export REFLEXION_API_KEY_ENV='OPENAI_API_KEY'
export REFLEXION_BASE_URL='https://api.openai.com/v1'

bash /absolute/path/to/reflexion/scripts/run_longcli.sh \
  /absolute/path/to/longcli-bench 61810_cow
```

直接用 `tb run` 时，传 `--model "$OPENAI_MODEL" --agent-kwarg api_key_env=OPENAI_API_KEY --agent-kwarg base_url=https://api.openai.com/v1`。其他供应商同理。模型必须支持 Chat Completions 形式且由账号实际提供，本项目不会猜测模型 ID。

地址优先级为显式 `base_url`，其次 `DEEPSEEK_BASE_URL`、`DEEPSEEK_API_BASE`、`OPENAI_BASE_URL`、`OPENAI_API_BASE`，最后为 DeepSeek 默认地址。脚本的 `REFLEXION_BASE_URL` 会变成显式参数，可避免环境里残留其他供应商地址。`REFLEXION_MODEL` 只供脚本覆盖模型；适配器本身接受 `model_name`、`DEEPSEEK_MODEL` 或 `OPENAI_MODEL`。

`ReflexionConfig` 和 `ModelConfig` 的字段均可通过重复 `--agent-kwarg 名称=值` 设置；拼错字段或非法类型会立即报错。`no_rebuild` 是上游自动注入参数，会被接受。`version` 与 `prompt_template` 交给 `BaseAgent`。密钥只通过环境变量传入。固定版本的 [CLI](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/cli/tb/runs.py) 以不限制次数的 `split("=")` 解析参数，因此值含额外 `=` 会在到达适配器前失败；这类复杂值应改为程序化配置。

## 反思试次与基准轮数

| 参数 | 含义 |
| --- | --- |
| `--agent-kwarg max_trials=3` | 一次 `perform_task` 内最多 3 个 Reflexion 试次；评价未通过时生成反思，下一试次重建对话并读取有限反思记忆。 |
| `--give-test-output 1` | 官方评测总轮数为 1；代理结束后进行官方测试，没有额外测试反馈修复轮。 |
| `--n-attempts 3` | 官方 3 次独立尝试，用于多次尝试统计；不等于内部反思试次。 |

内部试次沿用同一终端、文件和进程，**没有环境重置**。这是面向 CLI 持续修复的适配选择，不能描述为论文环境可重置实验的逐项复刻。

官方 [harness](https://github.com/finyorko/longcli-bench/blob/2015f37b5c458f2562354de6b415e9182c91af64/terminal_bench/harness/harness.py) 在反馈轮间保留容器，但每轮新建 agent，并传入原任务及上轮测试反馈。适配器没有跨 `perform_task` 持久化反思记忆；默认 `--give-test-output 1` 避免把额外官方反馈混入内部机制。基准没有向 `BaseAgent` 提供评价器回调或环境重置函数，官方测试在代理返回后执行。

内部 Evaluator 依据可见轨迹、公开测试或自己编写的检查结果评价，并不拥有隐藏正确性判据。Actor 可以运行任务项目中可见的构建、单元测试和烟雾测试；适配器不自行调用官方隐藏测试，不读取宿主机的测试目录。`evaluator_passed` 和 `FailureMode.NONE` 都不表示官方成功；`result.json` 中 `official_success` 保持 `null`，官方 F2P/P2P 与步骤分数由基准计算。

## 预算、日志与错误

Actor、Evaluator、Reflection 的调用共用请求、token 和时间预算。`max_total_seconds` 是适配器内部预算；上游 `--global-agent-timeout-sec` 应略大以容纳初始化和写日志。底层网络和上游线程超时不保证立即终止进程，严格截止时间由外部进程或容器监管提供。

每次 `perform_task` 写入 `<logging_dir>/reflexion/<唯一ID>/events.jsonl` 和 `result.json`；同一目录的多次调用不会覆盖，反思内容和各试次记录可单独审计。日志脱敏器接收密钥环境变量值。原生 `AgentResult` 返回本次调用中全部角色的 token 用量；若启用多个官方反馈轮，跨轮费用应汇总每个唯一目录的 `result.json`，因为上游顶层 token 字段会被后轮覆盖。

| 停止原因 | 原生 FailureMode |
| --- | --- |
| `protocol_error` | `FATAL_LLM_PARSE_ERROR` |
| `max_total_seconds_reached` | `AGENT_TIMEOUT` |
| 模型、终端、评价或反思错误（`error` 非空） | `UNKNOWN_AGENT_ERROR` |
| 评价通过或次数预算耗尽且无执行错误 | `NONE` |

离线接口检查（不调用模型、不启动 Docker）：

```bash
cd /absolute/path/to/reflexion
python -m pip install -e '.[test]'
python -m pytest -q tests/test_longcli.py --basetemp .test-tmp-longcli
```

请先按固定提交检查安装和模型端点，再由实验执行者运行任务。本交付不报告成功率、成本结论或性能对比。
