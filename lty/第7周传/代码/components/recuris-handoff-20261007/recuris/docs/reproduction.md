# 论文、官方实现与 LongCLI 迁移

主要依据是用户提供的 36 页 `baseline/recuris.pdf`：*Recursive Experiential–Working Memory Evolution for Long-Horizon Agent Harnesses*，arXiv:2608.24876v1，2026-08-25。源文件 SHA-256 为 `dfa6f6d1174ad07dee26e5e3d310b750280fe3eaba16b371ef1e0d80bce8ae41`。

核对了作者 [Gen-Verse/Recuris](https://github.com/Gen-Verse/Recuris/tree/7d3745ab787b1206ccd981cb1511100476097266) 提交 `7d3745ab787b1206ccd981cb1511100476097266`。选取的终端适配、TTA、gate 与 seed 原始文件保存在 [upstream](upstream/README.md)，清单含逐文件 SHA-256，许可证和第三方说明原样保留。参考文件不在 Python 安装路径中执行。

## 论文机制对应

| 会议/预印本 PDF 位置 | 论文机制 | 交付实现 |
|---|---|---|
| p5 §2.1，式(2) | `M=(E,W,rho,C)`，基础模型/外层流程固定 | JSON 四组件；受限替换；不开放任意执行代码 |
| p6 式(3) | 结构化诊断轨迹 | 每步保存状态、技能、动作、观察、提议、checker 和提交后状态 |
| p7 §2.2.1 | goal 内容、pending/done/blocked、证据和 blocker | 目标账本与逐目标公开 verification |
| p7 §2.2.2 | event 驱动技能调用；terminal 默认 first_turn | 默认在第一步注入 E；可受限进化 rho |
| p7–8 式(5) | U 提议、C 检查、固定 K 提交 | 独立 W 更新请求和不可由模型绕过的 receipt 核验 |
| p8–9 式(7)–(8) | 归因到 E/W/rho/C，仅修改相关组件 | 诊断必须引用真实 trace step；每个组件单独 patch；其余保持相等 |
| p9 §2.3.3 | dev/anchor 验证后接纳或回滚 | 官方配对结果、固定 split、严格 gate 与原记忆回退 |
| p9 §2.3.4 | 有界递归；仅记忆层改变 | 接纳后的 JSON 可作为下一轮 base；内核、工具和 Meta 提示不改 |
| p10 §2.3.5、pp23–24 | 单任务 TTA，最多4次，只有失败bit，只改E | 外层独立 `tb run`、一次官方评分、E-only、首次成功停止 |
| p23 | TTA 与冻结记忆重试共享第一条轨迹 | `--seed-attempt-dir` 只读复用同配置、同任务的第一个 attempt |
| p10 | 温度0、200步、10次连续工具错误 | 温度和步数沿用；终端错误只累计有可靠回执的非零 check |

## 必须区分的复现边界

本实现复现方法结构和外部反馈信息边界，**没有进行原论文数值实验，也不是作者完整仓库的逐行等价移植**。

1. **环境和 Actor 不同。** 原终端实验为 Terminal-Bench 2.1、Harbor、Terminus-2；这里使用 LongCLI-Bench 原生 BaseAgent 和独立 JSON 终端 Actor，模型由接手者指定。不能把结果直接视为论文模型/基准成绩。
2. **W/C 更显式。** 作者当前终端 bridge 用任务文本建立一项 W，并使用最多两次拦截的启发式完成检查；它不证明 hidden correctness。本实现将任务分解为最多8个目标，并通过预先绑定的公开检查、随机 shell 回执、状态版本和文字条件提交 `done`。这是对论文式(5)在通用终端上的具体实现选择，会增加 W 调用和检查次数。
3. **核验只针对具体公开检查。** 模型仍负责提出目标和测试命令，可能漏掉要求或选择过弱的检查；确定性回执不能弥补这种语义不足。返回码0、内部 `task_complete` 和官方成功不等价。真正的官方成败仅由 LongCLI 测试计算。
4. **记忆序列化不同。** 作者采用 YAML manifest、Markdown E 卡和策略绑定；这里是可验证的 JSON 数据结构，不能直接加载原仓库所有 memory 包。本项目不加载任意 `local:` Python 插件。支持的 patch 范围是解释明确的子空间，不包括任意扩展 schema 或修改内核。
5. **两个 seed 明确区分。** `neutral` 的 E 为空，适合论文总体 M0 无经验概念。作者 `tb21_seed` 实际含一张 `terminal_closed_loop` 通用卡；`terminal` profile 保留其正文、first_turn 和8卡上限，W/C 用本迁移实现。新增描述和标签是元数据，正文来源原文件，许可见 `upstream/LICENSE`。它不是经过 LongCLI 演化的知识。
6. **调用时点。** 默认沿用论文 terminal 的 boundary first_turn。没有把 τ² 的 call-time 状态修改调用拦截伪装成 terminal 默认；也没有默认复刻当前作者主分支后来增加的错误触发检索和150轮后简化提示。rho 的可选新触发器属于本迁移的进化空间。
7. **上下文。** Actor 使用有限近期历史，并始终保留当前任务、W 和已经送达的 E；观察过长显式截断。Meta 对超长证据丢弃最旧完整步骤，记录 omitted step IDs。不是无损全文历史，也不是论文未公布的精确 token 预算。
8. **TTA 只用 E；跨任务另有 gate。** 官方失败bit不能替换成 LLM 自评。每次新的 `tb run` 创建独立 attempt；不利用 `--give-test-output>1` 延续同容器和暴露详细反馈。跨任务 gate 是独立接口，不能用于声称 task-local TTA 经过 held-out dev 验证。
9. **gate 阈值有区别。** 作者源码的多个入口也有差异：一个用配对 bootstrap 下界和回归上限，另一个要求净提升并单独报告显著性。本实现使用源失败修复、anchor 全保留、dev 均值不下降的固定保守规则，不计算统计显著性；见 [evolution.md](evolution.md)。
10. **没有学得记忆。** 跨任务和 TTA 代码交给接手者运行；本交付只含中性起点、实现和离线测试。生成候选不等于已经接纳；未执行的实验没有评分或成功率。

## 学习与评测的信息边界

单次代理只收到任务说明和任务终端。外层运行器在代理返回后读取官方 `is_resolved`，验证任务ID、trial名、评分完成状态、单反馈轮和完整文件后，产生一个 bool。

Meta 的输入仅从本代理的 `context.json` 和 `trace.json` 构建，附失败 bit；不把官方结果对象、测试脚本、控制台详情、参考答案或期望输出来回传模型。代码拒绝把评分对象塞进 trace schema。这个边界针对运行器的正常数据流，不能识别恶意文件所有者手工把秘密粘贴到普通字符串里的行为。

跨任务的 evolve/dev/test 按 task ID 分离；dev只进入 gate，不进入诊断提示；test完全不用于生成、筛选或接纳。使用方需要在实验前冻结 split；文件读取时的集合/哈希检查不能证明人为选择划分的时间。重复编号是配对采样编号，不保证不同服务端对同一编号产生确定性的随机样本。

原论文的“4次内成功”与“冻结适配后记忆再做4次完整采样”是不同实验。外层 `tta` 实现前者。若运行者研究 avg@4，应冻结最终记忆、另启独立评测，不把截断在首次成功的结果冒充 avg@4。
