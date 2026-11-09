# 通用基础层来源

本项目在当前工作区 `retrac` 工程的通用基础层上复用了以下代码与测试：

| 本项目文件 | 工作区来源 | 用途与调整 |
| --- | --- | --- |
| `src/reflexion/client.py` | `retrac/src/retrac/client.py` | 标准库 HTTP Chat Completions 客户端；保留接口、重试、超时、用量及错误脱敏；拒绝把布尔值作为超时或采样参数。 |
| `src/reflexion/audit.py` | `retrac/src/retrac/audit.py` | JSONL 事件、原子 JSON 快照以及常见凭据脱敏；通用逻辑保持不变。 |
| `src/reflexion/response_text.py` | `retrac/src/retrac/response_text.py` | 仅去除开头完整的小写 `<think>…</think>`；移除算法专属描述。 |
| `tests/test_client.py` | `retrac/tests/test_client.py` | 使用内存假传输检查请求、重试、截止时间、响应和日志；更新包路径与参数校验用例。 |
| `tests/test_response_text.py` | `retrac/tests/test_response_text.py` | 复用与文本边界有关的测试，删除旧工程特有状态格式测试。 |

这些文件只承担网络传输、响应文本边界处理、日志及离线校验，不构成 Reflexion 论文算法的来源。Actor、Evaluator、自我反思与跨试次文本记忆逻辑由本项目独立实现；不能把工作区旧工程的算法视为 Reflexion 的复现依据。

## LongCLI-Bench 接口与许可

`vendor-contracts/` 的以下四个文件从工作区 `retrac/vendor-contracts/` 逐字节复制，未修改内容：

- `terminal_bench__agents__base_agent.py`
- `terminal_bench__agents__failure_mode.py`
- `LICENSE`
- `manifest.json`

清单记录的上游是 <https://github.com/finyorko/longcli-bench>，提交为 `2015f37b5c458f2562354de6b415e9182c91af64`。`manifest.json` 保留原始下载地址与 SHA-256 校验值；`LICENSE` 保留上游 Apache-2.0 许可全文。这些文件仅用于离线接口契约检查，不是可运行的 LongCLI-Bench 副本。

## 基础层接口

- `ModelConfig` 必须显式给出 `model_name`。`api_key_env` 默认为 `DEEPSEEK_API_KEY`；客户端仅读取指定环境变量，适配器负责选择变量名称。
- 服务地址优先使用 `base_url`，然后依次读取 `DEEPSEEK_BASE_URL`、`DEEPSEEK_API_BASE`、`OPENAI_BASE_URL`、`OPENAI_API_BASE`，最后默认 `https://api.deepseek.com`。地址可包含 `/v1` 或完整 `/chat/completions` 路径。
- `OpenAIChatClient.complete(messages, *, purpose, deadline_monotonic=None)` 返回 `ModelReply`，包含正文、输入/输出 token 用量及结束原因。接口不执行模型返回的工具调用。
- `JsonlLogger(directory, *, secrets=())` 提供 `write(event, **payload)` 与 `save(name, value)`；脱敏是尽力而为的凭据过滤，不是完整的数据匿名化。
- `strip_reasoning_prefix(text)` 只移除完整的开头 `<think>` 区块；未闭合的开头区块抛出 `ReasoningPrefixError`，正文中的标签原样保留。

客户端截止时间会限制单次 socket 超时与重试等待；持续传输字节的 HTTP 响应仍需外部进程/容器的硬超时管理。离线测试使用假客户端，不调用模型 API、Docker 或 benchmark 实验。
