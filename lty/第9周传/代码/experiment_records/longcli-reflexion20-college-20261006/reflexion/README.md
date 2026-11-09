# Reflexion × LongCLI-Bench

根据用户提供的 NeurIPS 2023 论文 **Reflexion: Language Agents with Verbal Reinforcement Learning**，实现 Actor、Evaluator、Self-Reflection 和有界反思记忆，并通过原生 `BaseAgent` 接口接入 [LongCLI-Bench](https://github.com/finyorko/longcli-bench)。

**本目录可独立交接，不依赖旁边的 `retrac` 项目。没有运行真实模型请求、Docker 任务或基准实验，也没有性能结果。** 本实现是 Reflexion 的终端领域适配：同一个容器内多次修复，重启 Actor 对话，保留任务文件和进程状态；不等同于原论文 ALFWorld 的环境重置实验。完整对应关系与差异见 [复现说明](docs/reproduction.md)。

## 交给运行者

直接发送 `dist/reflexion-handoff.zip`，解压后得到完整 `reflexion/` 源码目录；也可以复制本目录。压缩包内 `MANIFEST.sha256` 记录逐文件校验值，压缩包外同名 `.sha256` 文件记录整个包的校验值。不包含密钥、模型运行日志或任务数据。

推荐 Linux 或配置好 Docker 的 WSL2。官方 LongCLI 需要 Python 3.12+、Docker、Docker Compose、uv。以下命令供接手者执行，本次未执行。

```bash
git clone https://github.com/finyorko/longcli-bench.git
cd longcli-bench
git checkout 2015f37b5c458f2562354de6b415e9182c91af64
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uv pip install -e /absolute/path/to/reflexion

# LongCLI 提供的任务基础镜像
cd longcli_dockerImage
docker build -f Dockerfile.make-pytest-base -t tb/make-pytest:v0 .
docker build -f Dockerfile.c-env-base -t tb/c-env:v0 .
cd ..

export DEEPSEEK_API_KEY='由运行者设置'
export DEEPSEEK_MODEL='账号可用的模型ID'
# 默认 https://api.deepseek.com；兼容服务可指定根地址或 /v1 地址
# export DEEPSEEK_BASE_URL='https://your-provider.example/v1'

python -m reflexion doctor
bash /absolute/path/to/reflexion/scripts/run_longcli.sh \
  /absolute/path/to/longcli-bench 61810_cow
```

请安装指定的 **LongCLI 官方仓库**；仅安装同名 PyPI `terminal-bench` 不能确认具备 LongCLI 的评分扩展。`doctor` 仅检查配置存在和适配器可导入，不发网络请求，也不证明 Docker、模型端点或基准提交正确。

启动脚本要求明确给出任务 ID；整个数据集使用 `--all`。第三个参数起传给 `tb run`，例如 `--output-path /data/reflexion-runs`。运行其他兼容模型和官方评分汇总见 [接口与运行说明](docs/longcli-contract.md)。

也可以直接运行：

```bash
tb run \
  --agent-import-path reflexion.longcli:ReflexionAgent \
  --model "$DEEPSEEK_MODEL" \
  --dataset-path /absolute/path/to/longcli-bench/tasks_long_cli \
  --task-id 61810_cow \
  --output-path ./runs_reflexion \
  --run-id reflexion-example \
  --n-attempts 1 --give-test-output 1 --n-concurrent 1 \
  --agent-kwarg max_trials=3 \
  --agent-kwarg memory_size=3 \
  --agent-kwarg max_total_seconds=3600 \
  --global-agent-timeout-sec 3900
```

不要同时传 `--agent`。模型通过环境变量读取密钥，避免把密钥写进命令行和提交包。

## 实现的循环

1. **Actor**：基于原任务、当前终端观察和最近的反思，执行 ReAct 风格的多步终端操作；操作只能发到官方提供的任务会话。
2. **Evaluator**：Actor 声明结束后，由独立提示的模型判断可见证据是否满足任务；循环、步骤或上下文上限则由失败启发式给出反馈。
3. **Self-Reflection**：若失败且还有重试预算，输入本次轨迹、评估反馈和已有记忆，生成失败原因与下一轮可执行的改进计划。
4. **Memory**：将反思追加到 FIFO 记忆，只保留最近 `memory_size` 条。下一轮重新创建 Actor 对话；不拼接旧的完整轨迹。内部自评通过或达到预算即停止。

三种角色使用同一配置的模型，但调用与提示独立。反思不是训练，不更新权重，也不是把报错直接追加给 Actor。最后一轮失败后没有后续重试，因此不再花费一次调用生成未使用的反思。每次 `perform_task` 的记忆从空开始，任务之间不共享。

**内部 `passed=true` 不等于官方成功。** 官方隐藏测试在 `perform_task` 返回后由 harness 执行；本适配器不调用隐藏测试、不读取标准答案，也不自行计算 F2P/P2P 或官方通过率。内部评估只能看到任务已有公开测试、自建测试、构建及其他终端证据；模型可能误判。日志的 `official_success` 始终是 `null`。

## 次数和预算

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `--agent-kwarg max_trials` | 3 | 一次代理调用内的总 trial 数，包含首次执行；失败后才重试 |
| `--give-test-output` | 脚本设为 1 | 官方测试反馈总轮数；1 表示没有额外带官方测试反馈的修复轮 |
| `--n-attempts` | 脚本设为 1 | 独立基准 attempt 数；不等于 Reflexion trial 数 |

为避免把官方测试反馈修复混入内部反思，默认 `--give-test-output 1`。上游每个官方反馈轮会重建代理；若增加该值，本实现不会跨反馈轮读取过去日志恢复记忆，所得设置应单独报告。

算法配置都可通过重复的 `--agent-kwarg 名称=值` 设置：

| 配置 | 默认 | 说明 |
|---|---:|---|
| `memory_size` | 3 | 最近反思条数；论文常用 1–3 |
| `max_steps_per_trial` | 40 | 每 trial 的有效 Actor 响应上限，包含结束响应；格式修复计入模型调用 |
| `repeat_action_limit` | 4 | 连续相同非空按键与相同输出触发失败反思；空按键轮询不计 |
| `max_tool_calls` | 120 | 全部 trial 共享终端调用上限，轮询也计一次 |
| `max_model_calls` | 256 | Actor、自评、反思及格式修复共享逻辑调用上限 |
| `max_total_seconds` | 3600 | 内部墙钟时间上限，覆盖全部角色与终端等待 |
| `max_context_chars` | 120000 | 输入字符上限，**不是 token 窗口** |
| `context_reserve_chars` | 16000 | Actor 为评估、反思和后续响应预留的字符空间 |
| `max_observation_chars` | 16000 | 单条观察展示上限，超出保留头尾并显式标注截断 |
| `max_reflection_chars` | 4000 | 单条反思长度上限；超出则要求重写 |
| `max_command_duration` | 120 | 单次终端等待秒数；长任务可用空按键轮询 |
| `max_parse_attempts` | 2 | 各角色格式校验的总尝试次数，不是额外重试次数 |

预算值是本次 CLI 迁移的工程默认值，不代表论文原实验全部超参数。若最后一轮未完成，不会用上一轮答案冒充。上下文不足时会结束当前 trial；评估和反思输入过长时只做明确标记的头尾截断，不使用其他论文的递归摘要算法。

模型配置：`base_url`、`api_key_env`（默认 `DEEPSEEK_API_KEY`）、`timeout_seconds=120`、`max_attempts=3`（单次调用 HTTP 尝试次数）、`max_output_tokens=4096`，以及可选 `temperature`、`top_p`、`reasoning_effort`、`extra_body` JSON。不默认传入供应商可能不支持的采样参数。`max_completion_tokens` 可通过 `extra_body` 设置。

字符预算不能精确保证模型 token 窗口；运行者需要按模型调整。HTTP socket 超时与上游线程超时都不等于强制终止进程；需要严格截止时由运行环境提供进程或容器监管。HTTP 重试计为同一个逻辑模型调用。

## 日志和离线验证

每次代理调用写入 `<logging_dir>/reflexion/<唯一ID>/`：

- `events.jsonl`：分角色模型请求/响应、实际终端输入和原始观察、评估、反思、记忆及停止原因。
- `result.json`：逐 trial 的评估与反思、最后 trial 答案、总模型/工具次数、token 用量、耗时和错误位置。

模型用量汇总包含自评、反思和格式修复；API 未报告的失败请求用量无法推断。上游多反馈轮的顶层 token 字段存在覆盖行为，跨轮成本请汇总上述唯一目录的日志。日志脱敏是尽力过滤，分享前仍需按任务数据检查敏感内容。

以下仅运行固定响应与内存终端的单元/接口测试，不需要 API 密钥、真实模型或 Docker：

```bash
cd /absolute/path/to/reflexion
python -m pip install -e '.[test]'
python -m pytest -q --basetemp .test-tmp-local
python -m reflexion config
python -m reflexion --help
```

验证范围与交付记录见 [离线验证说明](docs/validation.md)。真实模型和 Docker 的端到端兼容性由接手者运行时确认。

## 文件导航

- `src/reflexion/engine.py`：完整 Reflexion 状态机和共享预算。
- `src/reflexion/prompts.py`：Actor、Evaluator、Self-Reflection 三个终端领域提示。
- `src/reflexion/protocol.py`：动作与评价协议，全批次校验后才执行。
- `src/reflexion/longcli.py`：官方 `BaseAgent` 与 `TmuxSession` 适配。
- `src/reflexion/client.py`：可配置的兼容 Chat Completions 客户端。
- `scripts/run_longcli.sh`：交给运行者的启动脚本。
- `vendor-contracts/`：离线契约测试使用的固定提交官方类型、来源清单与 Apache-2.0 许可。

这是依据论文的独立实现，不是作者或 LongCLI 官方发布版本。论文和上游来源见 [复现说明](docs/reproduction.md)；通用工程层复用记录见 [来源说明](docs/infrastructure-provenance.md)。
