# 离线验证记录

验证日期：2026-10-06。环境：Windows，Python 3.12.5。只使用固定响应的模型替身、内存中的终端会话，以及本地接口类型；未连接模型 API、未启动 Docker、未运行 LongCLI-Bench 任务，也没有生成任何性能结果。

## 已完成

```text
python -m pytest -q --basetemp .test-tmp-final
115 passed, 33 subtests passed in 1.59s
```

- 核心循环：失败评价、归因反思、下一 trial 新对话、同环境持续、FIFO 容量、不同任务之间记忆隔离、成功和预算停止、末轮答案处理。
- 协议和预算：整批动作校验后执行，拒绝无证据的通过结构、非布尔标记和非法持续时间；截断响应不执行；模型调用、工具调用、时间和上下文限制；全部角色及失败响应的已知 token 记账。
- 长终端任务：原样传递 heredoc、换行和 Ctrl-C，空按键轮询，重复失败检测，观察和审查输入的明确截断。
- 客户端和日志：兼容请求结构、临时失败重试、截止时间、错误和凭据过滤、原子 JSON 快照。
- 原生接口：加载固定上游提交的 `BaseAgent`、`AgentResult`、`FailureMode`；检查 kwargs、用量、错误映射与不同调用的日志目录。
- 接缝集成：真实 `ReflexionAgent` → 真实 `ReflexionRunner` → 内存终端，使用固定模型响应完成两轮失败反思及自评通过，核对全部七次角色调用、记忆、事件和原生返回结果。

此外，`python -m reflexion --help` 和 `python -m reflexion config` 可用；所有源码及打包脚本通过 Python AST 语法解析，`pyproject.toml` 可解析。启动脚本使用 LF 换行。

## 交接包检查

`python scripts/build_handoff.py` 只打包明确列出的源码、测试、说明、脚本和接口许可证，排除缓存、离线测试临时数据、运行目录和环境文件。脚本为源文件生成 SHA-256 清单，写出 ZIP 后再次逐文件比较内容并检查 ZIP CRC；额外生成整个压缩包的 SHA-256。

## 尚未验证

- 真实模型端点的参数兼容性、任务成功率、成本和时延。
- Linux/WSL 与真实 Docker/tmux 环境中的端到端运行。
- Bash 脚本经过源码检查，本机没有可用的 Git Bash / 已验证 Linux shell，未执行 `bash -n` 或启动命令。

内部 Evaluator 的证据仍是模型判断，结构校验不能证明判断正确；`evaluator_passed` 不等于官方成功。离线测试全部通过只说明上述代码路径与接口契约得到检查，不能替代实际基准评测。

接手者按 [README](../README.md) 安装固定版本基准和本适配器，再自行执行实验即可。任何实验报告应记录模型、端点、预算、`max_trials`、`--give-test-output` 和 `--n-attempts`，不能把三类次数混为一谈。
