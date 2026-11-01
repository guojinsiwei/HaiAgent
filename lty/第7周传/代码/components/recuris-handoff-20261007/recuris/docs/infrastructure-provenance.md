# 通用基础层来源

本项目从当前工作区的 `reflexion` 工程复用了下列通用代码和离线测试。文件均已放入本项目；运行和安装不需要 `reflexion` 或 `retrac` 包。

| 本项目文件 | 工作区来源 | 用途与调整 |
| --- | --- | --- |
| `src/recuris/client.py` | `reflexion/src/reflexion/client.py` | 标准库 HTTP Chat Completions 客户端；保留请求参数、重试、截止时间、用量及错误脱敏接口，内容未改动。 |
| `src/recuris/audit.py` | `reflexion/src/reflexion/audit.py` | JSONL 事件、原子 JSON 快照以及常见凭据脱敏，内容未改动。 |
| `src/recuris/response_text.py` | `reflexion/src/reflexion/response_text.py` | 仅去除开头完整的小写 `<think>…</think>` 区块，内容未改动。 |
| `tests/test_client.py` | `reflexion/tests/test_client.py` | 使用内存假传输检查请求、重试、截止时间、响应和日志；仅更新包导入与 mock 路径。 |
| `tests/test_response_text.py` | `reflexion/tests/test_response_text.py` | 仅保留独立文本边界测试，移除旧算法协议导入与两个旧协议用例。 |
| `src/recuris/longcli.py` | `reflexion/src/reflexion/longcli.py` | 复用 native `BaseAgent`、tmux 原始按键桥接、参数转换、用量与错误映射；替换为 Recuris 单次执行配置，加入独立 Skill Memory 加载及 temperature=0 默认值。 |
| `tests/test_longcli.py` | `reflexion/tests/test_longcli.py` | 复用上游原始契约加载器与桥接测试；替换旧算法参数/停止状态，新增独立记忆、温度默认值和真实 Recuris 内核接缝校验。 |
| `scripts/run_longcli.sh` | `reflexion/scripts/run_longcli.sh` | 复用环境检查与原生 `tb run` 调用结构；使用 `RECURIS_*`、单次执行步数上限、外部 memory 文件和独立外层反馈次数。 |

这些文件承担网络传输、响应文本处理、日志和离线校验，不构成 Recuris 论文算法的来源。`reflexion` 的来源说明记录这些基础层更早来自本工作区 `retrac` 的通用基础设施。算法实现和论文对应关系以本项目的复现说明为准。

## LongCLI-Bench 接口与许可

`vendor-contracts/` 的以下四个文件从工作区 `reflexion/vendor-contracts/` 逐字节复制，未修改内容：

- `terminal_bench__agents__base_agent.py`
- `terminal_bench__agents__failure_mode.py`
- `LICENSE`
- `manifest.json`

清单记录的上游是 <https://github.com/finyorko/longcli-bench>，提交为 `2015f37b5c458f2562354de6b415e9182c91af64`。`manifest.json` 保留原始下载地址与 SHA-256 校验值；`LICENSE` 保留上游 Apache-2.0 许可全文。这些文件仅用于离线接口契约检查，不是可运行的 LongCLI-Bench 副本。本次复制未重新获取上游，也不表示已核验该提交之后的接口变化。

## 基础层接口

- `ModelConfig` 必须显式给出 `model_name`。`api_key_env` 默认为 `DEEPSEEK_API_KEY`；客户端仅读取指定环境变量，适配器负责选择变量名称。
- 服务地址优先使用 `base_url`，然后依次读取 `DEEPSEEK_BASE_URL`、`DEEPSEEK_API_BASE`、`OPENAI_BASE_URL`、`OPENAI_API_BASE`，最后默认 `https://api.deepseek.com`。地址可包含 `/v1` 或完整 `/chat/completions` 路径。
- `OpenAIChatClient.complete(messages, *, purpose, deadline_monotonic=None)` 返回 `ModelReply`，包含正文、输入/输出 token 用量及结束原因。接口不执行模型返回的工具调用。
- `JsonlLogger(directory, *, secrets=())` 提供 `write(event, **payload)` 与 `save(name, value)`；脱敏是尽力而为的凭据过滤，不是完整的数据匿名化。
- `strip_reasoning_prefix(text)` 只移除完整的开头 `<think>` 区块；未闭合的开头区块抛出 `ReasoningPrefixError`，正文中的标签原样保留。

客户端截止时间会限制单次 socket 超时与重试等待；持续传输字节的 HTTP 响应仍需外部进程或容器的硬超时管理。离线测试使用假传输，不调用模型 API、Docker 或 benchmark 实验。
