# 离线验证记录

验证日期：2026-10-07（Asia/Shanghai）。环境：Windows、Python 3.12.5。

运行 `python -m pytest -q --basetemp .test-tmp-final-20261007`：**274 passed，33 subtests passed**。全部使用预制模型回复、模拟终端/HTTP 或模拟 harness；没有发起真实模型请求、执行 `tb run`、启动 Docker 或运行 LongCLI 任务。

覆盖范围：

- 原生 `BaseAgent`/`AgentResult` 契约、参数转换与 tmux 按键转发；契约取自固定的 LongCLI 提交。
- 四组件记忆校验、first-turn 技能调用、结构化 W 更新、真实退出回执、命令回显排除、陈旧证据拒绝与预算退出。
- Meta 的真实步骤归因、组件限定修改、E-only TTA、上下文裁剪、无操作和错误处理。
- 独立 attempt、官方评分完成检查、隐藏反馈隔离、首次轨迹复用、来源/文件摘要一致性和不完整结果处理。
- 默认 CLI 模型选项、凭据参数拒绝、端点来源摘要、候选正文与摘要的持久化一致性。
- 跨任务来源/dev/test 隔离、完整配对矩阵、禁止重复 trial、模型/代码/预算一致性、gate 接纳和原记忆回退。

另已通过 Python 语法编译、`python -m recuris --help`/`config`、无网络 wheel 构建及 wheel 模块/两份 seed 资源检查；论文原文件与两组参考源码清单的 SHA-256 全部匹配，本项目文档的本地链接存在。当前机器没有可用的 Git Bash，未执行 `bash -n`；shell 入口尚需接手者在 Linux/WSL 中验证。

`scripts/build_handoff.py` 只打包源代码、测试、文档、参考契约与许可；校验 ZIP CRC、每个文件的字节和完整文件集合，另生成逐文件清单与压缩包 SHA-256。包内不包含本地测试临时目录、运行日志、PDF 原文或任务数据。

离线契约测试不能确认真实端点支持当前模型选项，也不能确认 Docker、任务数据、完整上游依赖及评分耗时。接手者应按 README 安装指定 LongCLI 提交并进行真实端到端验证。本交付没有论文复现成绩、学习后技能或基准成功率。
