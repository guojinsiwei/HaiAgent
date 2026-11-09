# RE-TRAC × LongCLI-Bench

依据用户提供的 [RE-TRAC 论文 v1](https://arxiv.org/abs/2602.02486v1)，实现训练无关的递归轨迹压缩，并接入 [LongCLI-Bench](https://github.com/finyorko/longcli-bench) 原生 Agent 接口。默认使用 **DeepSeek 兼容 API**，具体模型由运行者指定。

本交付包含实现、测试和运行说明。**没有运行模型实验或 LongCLI-Bench 评测，不包含性能结果。** 离线测试验证递归状态、预算、协议解析和原生接口；真实 Docker 和模型端点联调由接手者完成。

## 直接交给运行者

1. 将本目录完整复制给运行者，或发送 `retrac-handoff.zip` 并解压。
2. 按 [LongCLI 接口与环境说明](docs/longcli-contract.md) 安装固定版本的官方基准及所需容器镜像。
3. 在基准使用的同一 Python 环境中安装本适配器：

   ```bash
   python -m pip install -e /absolute/path/to/retrac
   export DEEPSEEK_API_KEY='由运行者填入'
   export DEEPSEEK_MODEL='运行者账号可用的模型ID'
   # 使用代理地址时设置；默认 https://api.deepseek.com
   # export DEEPSEEK_BASE_URL='https://your-compatible-endpoint/v1'
   ```

4. 在 Linux / WSL 中启动指定任务（以下命令本次未执行）：

   ```bash
   bash /absolute/path/to/retrac/scripts/run_longcli.sh \
     /absolute/path/to/longcli-bench 61810_cow
   ```

脚本只组装官方 `tb run` 命令；不安装环境、不下载任务。任务 ID 必须存在于 `tasks_long_cli/`。第三个参数以后会传给 `tb run`，例如 `--output-path /data/retrac-runs`。如需整个数据集，将任务 ID 写成显式的 `--all`。

也可以直接调用：

```bash
tb run \
  --agent-import-path retrac.longcli:RetracAgent \
  --model "$DEEPSEEK_MODEL" \
  --dataset-path /absolute/path/to/longcli-bench/tasks_long_cli \
  --task-id 61810_cow \
  --n-attempts 1 --give-test-output 1 --n-concurrent 1 \
  --agent-kwarg rounds=8 \
  --agent-kwarg max_total_seconds=3600 \
  --global-agent-timeout-sec 3900
```

不要同时传 `--agent`。本项目固定核对的官方提交是 `2015f37b5c458f2562354de6b415e9182c91af64`；若换基准版本，先核对接口。

## 机制与配置

每轮执行 ReAct 风格终端交互，然后计算 `S_t = Compress(轨迹_t, S_(t-1))`。下一轮从原任务和最新状态重新开始对话，终端、文件和进程保持当前状态。默认运行 8 轮，输出末轮答案；模型自报完成不会提前结束整个递归流程。基准通过率由官方测试决定。

压缩默认采用图 10 的 full 八项结构，也可选择图 9 的 base 五项。压缩调用与求解使用同一模型，计入同一时间、请求和 token 统计。图 11 的续跑提示保留对摘要的怀疑及重新探索机制。完整对应关系见 [复现说明](docs/reproduction.md)。这里复现推理框架，不包含 RE-TRAC-4B/30B 的 SFT 训练。

所有配置通过 `--agent-kwarg 名称=值` 传入：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `rounds` | 8 | RE-TRAC 内部轨迹轮数；1 可作为相同终端协议的单轮基线 |
| `summary_variant` | full | full / base |
| `max_steps_per_round` | 50 | 每轮行动响应上限；达到后压缩续轮 |
| `max_tool_calls` | 400 | 所有轮共享的终端调用上限；每条命令/轮询计一次 |
| `max_model_calls` | 512 | 逻辑模型调用总上限，含压缩和格式修复 |
| `max_total_seconds` | 3600 | 内部墙钟预算 |
| `max_context_chars` | 180000 | 上下文字符限制，**不是模型 token 窗口** |
| `compression_reserve_chars` | 20000 | 为下一响应及压缩留出空间 |
| `max_observation_chars` | 24000 | 单次观察上限，超出则明确截断；剩余空间不足时更小 |
| `max_state_chars` | 48000 | 压缩状态字符上限 |
| `max_command_duration` | 120 | 单次终端等待秒数；长进程通过空按键轮询 |
| `max_parse_attempts` | 2 | 行动/状态格式修复的最大尝试次数 |
| `base_url` | DeepSeek 地址/环境变量 | 兼容服务根地址或 `/v1` 地址 |
| `api_key_env` | DEEPSEEK_API_KEY | 存放密钥的环境变量名 |
| `timeout_seconds` | 120 | 单次 HTTP 阻塞超时，同时受剩余任务时间约束 |
| `max_attempts` | 3 | 单个逻辑模型调用的最大 HTTP 尝试次数 |
| `max_output_tokens` | 4096 | 单次生成上限；压缩经常截断时应增加 |
| `temperature` / `top_p` / `reasoning_effort` | 不传 | 仅设置目标端点支持的参数 |
| `extra_body` | 不传 | 可选 JSON 对象，用于端点特有参数 |

`--give-test-output 1` 是官方评测总轮数，防止把带测试反馈的额外修复混作 RE-TRAC 内部递归。它与 `rounds=8`、`--n-attempts` 的含义不同。

预算边界属于 CLI 迁移的工程配置，不能称为原论文全部实验超参数。未完成 K 轮或末轮无最终回答时会保留实际停止原因；不会用前轮答案冒充末轮答案。终端内的真实文件仍交给官方评测器评分。

## 日志与离线验证

每次官方 `perform_task` 调用输出到 `<logging_dir>/retrac/<唯一ID>/`：

- `events.jsonl`：模型请求/响应、每条实际输入、终端反馈、压缩状态、预算与错误事件。
- `result.json`：逐轮结果与状态、最后答案、工具/模型次数、token 用量、停止原因及耗时。`official_success` 固定为 null。

HTTP 重试不单独计入 `max_model_calls`。token 采用 API 报告的用量；没有返回用量的网络失败无法推断实际账单。日志会过滤配置密钥和常见凭据格式，仍需按任务数据的敏感程度管理日志。字符限制不能保证适合所有模型的 token 窗口，运行者须按模型调整。

内部截止时间会约束请求、重试及终端等待。底层 socket 的超时不等价于强制终止线程，上游也可能用线程执行；需要严格的进程级截止时间时，由运行环境的进程/容器监管负责。

不使用密钥、Docker或付费 API 的离线检查：

```bash
cd /absolute/path/to/retrac
python -m pip install -e '.[test]'
python -m pytest -q --basetemp .test-tmp-local
python -m retrac --help
```

`python -m retrac demo --output runs/demo` 可运行内存中的固定两轮示例；它不执行真实 shell，也不是实验。`python -m retrac doctor` 只检查环境变量是否存在及适配器能否导入，不连模型端点。

## 文件入口

- `src/retrac/longcli.py`：LongCLI 原生适配器与 tmux 桥接。
- `src/retrac/engine.py`：递归执行、状态校验及全局预算。
- `src/retrac/prompts.py`：论文图 9—11 与终端协议。
- `src/retrac/client.py`：DeepSeek 兼容 HTTP 客户端。
- `src/retrac/audit.py`：日志及凭据过滤。
- `docs/longcli-contract.md`：基准安装、镜像和版本接入详情。
- `vendor-contracts/`：离线契约测试使用的官方接口快照及原许可证。

模型协议依据 [DeepSeek Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)。本目录是基于论文的独立实现，不是微软或 LongCLI-Bench 官方发布版本。
