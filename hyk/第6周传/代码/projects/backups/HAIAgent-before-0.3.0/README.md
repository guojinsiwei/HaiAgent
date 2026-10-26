# HAIAgent

一个单路径 CLI Agent：**模型负责下一步行动和何时提交；组件提供结构化上下文与任务内记忆；独立评测器决定是否成功。** 不使用 BestFGS 树搜索、候选排名、内部成功评分、强制提交前复测或额外 LLM 总结。

这是新的独立工程，提取了 BestFGS v14 的必要基础设施并重新组织；不依赖旧项目的安装路径，不修改旧实验。Python 3.11+，标准库即可运行。包含 `hai` 和 `raw` 两种模式，后者用于共享执行、预算、提交和测量协议的对照。

## 当前能做什么

- 调用配置的 Chat Completions 兼容 API，模型每轮只需选择一条命令或提交。
- 在一个持续存在的任务工作区执行命令，不每步复制仓库。每次命令是新进程，`cd`/`export` 不跨调用保存；文件与服务状态可以持续存在。
- HAIAgent 接入有界上下文与记忆组件；Raw 保留普通历史，不启用该组件。
- Git 任务导出相对于初始固定提交的补丁，包括新增、删除、暂存和未暂存文件；不依赖模型手写 diff。
- Terminal 任务提交当前环境状态的描述，并交给外部 harness 在同一环境评测；不强制要求 Git 或补丁。
- 保存可追溯事件、实际模型请求次数、token 用量覆盖情况、交互轮次、工具调用及有界审计证据。
- 导入独立测试报告，导出语义冗余审计资料，按冻结题单汇总配对实验。

**当前没有启动付费实验，也没有声称通过 SWE-bench 或 Terminal-Bench。** 官方环境准备、Docker/Harbor 生命周期、隐藏测试仍由外部 benchmark harness 管理。本工程提供运行及数据契约，不冒充完整的官方评测器适配。

## 快速验证

Windows PowerShell，在工程目录执行：

```powershell
.\hai.ps1 demo --out .\runs\demo-001
.\test.ps1
```

`demo` 使用脚本策略而不是真实模型，实际执行“读取 → 修改 → 测试 → 提交”，输出补丁和独立的示例断言结果。不会访问付费 API。每次使用新的输出目录，已有目录不会覆盖。

Linux / 已安装 Python 的环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
hai-agent demo --out runs/demo-001
python -m unittest discover -s tests -v
```

## 启动真实任务

先准备**可丢弃、已隔离**的任务环境，然后编辑 `examples/task.json` 与 `examples/config.json` 的副本：

- `task_id`：原始 benchmark 题号。
- `instruction`：公开题面；不得含隐藏测试、参考答案或官方测试补丁。
- `workspace`：已准备好的任务工作区，不是 HAIAgent 工程目录。
- `delivery`：SWE 类修改仓库任务用 `git_patch`；Terminal 类环境任务用 `terminal`。
- `api.base_url`、`api.model`：你确认可用的端点和实际模型 ID。示例中的模型名是占位符，不会自动替你切换模型。
- `method`：`hai` 或 `raw`。配对时除这一项外，共用模型、端点、预算、工具权限和初始任务环境。
- `environment`：确实需要传给命令的非控制器环境变量。控制器 Key 不传给命令子进程。

在本机安全输入 Key（不写入配置文件或命令行参数）：

```powershell
$haiSecret = Read-Host 'API Key' -AsSecureString
$env:HAI_API_KEY = [System.Net.NetworkCredential]::new('', $haiSecret).Password
try {
    .\hai.ps1 run --task .\my-task.json --config .\my-config.json --out .\runs\task-001-hai --allow-local-execution
} finally {
    Remove-Item Env:HAI_API_KEY -ErrorAction SilentlyContinue
}
```

`--allow-local-execution` 是明确执行许可，不是安全隔离开关。模型可以通过 Python/bash 执行任意代码；cwd 边界检查和环境变量过滤**不是沙箱**。真实基准应在专用 Docker/VM 中运行，不要直接对个人桌面、共享科研目录或包含密钥的宿主运行模型命令。控制器的 HOME 文件权限、容器网络及资源限额需要由外部隔离层控制。

Windows 脚本优先使用 `HAI_PYTHON` 指定的解释器，其次寻找本机已存在的 Codex 配套 Python，再尝试 PATH 中的 Python；不绑定本机用户名，也不会自动下载安装依赖。

## 模型如何行动和提交

```json
{"action":"run","argv":["python","-m","pytest","tests/test_x.py"],"cwd":".","timeout_seconds":60,"purpose":"检查修复相关行为"}
```

```json
{"action":"submit","summary":"交付内容以及仍存在的不确定性"}
```

模型可以在任何有剩余决策预算的轮次提交；不要求附带新命令，不要求再次通过预设测试，也不由另一个模型打分放行。格式错误反馈给同一个策略模型，消耗下一轮预算，不隐藏额外的修复调用。

框架只检查交付契约：例如 Git 任务不能提交空补丁，不能因 Git 读取失败而假称已交付。拒绝后保留工作区并反馈原因。Terminal 任务没有“必须有补丁”的条件。提交后不继续偷偷优化；预算耗尽也不会冒充模型已提交。

允许模型自提交是待验证的设计选择，并不意味着强模型能可靠知道自己是否正确。提交率、官方成功率以及“已提交但未通过”的比例必须分开观察。

## 上下文和记忆怎样接入

每次模型请求优先保留任务、约束及最新的一对行动/反馈，HAI 与 Raw 都遵守这一规则；必要时显式截短文本，而不是把最新反馈整段丢掉。较大的历史 stdin 用长度和摘要代替。HAI 另提供有界状态/记忆块，不再在其中重复存放整份对话反馈；老轮次在剩余预算内保留。没有额外的记忆 LLM 请求。

默认记忆上限 12 条、12,000 序列化字节；近期缓冲最多 6 条、16,000 字节，另保留一条有界最新反馈。普通成功和单次一般报错不自动入库。

模型**可选**在正常行动里附带一条重要发现，而不是每轮被要求生成经验：

```json
{
  "action":"run",
  "argv":["cat","config.py"],
  "memory":{
    "conclusion":"配置项由 config.py 的项目配置加载流程读取",
    "applies_when":"查找这个项目的配置读取位置时",
    "evidence_ids":["E1"],
    "kind":"finding",
    "dependencies":["workspace"]
  }
}
```

必须引用本任务实际保留的证据，默认作为假设，不因反复出现就升级成已证明的因果规则。当前有效证据优先召回；旧版本或环境未知的经验仍可作为明确标记的 `historical_reference` 提醒，不冒充当前有效规则，也不禁止行动。匹配使用当前目标、命令和错误的轻量词项匹配，不是语义向量检索。

对无选项的简单 `cat/head/tail` 读取，记录稳定文件内容的指纹。单一来源、只依赖代码的 `finding` 可按该文件校验，不因无关日志变化或返回根目录而失效。文件变化立即降级；一般命令、shell 包装和多证据结论不猜测这种窄范围。最多跟踪 32 个文件，每个最多 2 MB，每轮刷新预算 0.5 秒；未知不当作没变。

**环境边界特别说明：** 文件指纹不能证明包、服务、网络状态不变。通用执行器在任意命令后将环境版本置为未知，因此依赖环境的自动经验不会被强行当作当前有效规则使用。代码局部发现可声明只依赖 `workspace`；环境相关结论不能这样缩小范围。专用环境适配器若要增强自动提取，需要提供真实的环境版本追踪，而不是填一个固定假值。这版优先保证来源和适用范围诚实，不宣称自动理解所有重要经验。

上下文中的片段不是可信指令；组件和 Agent 的数据标记不能完全防御提示注入。组件不保存无限原始 stdout，但测量层为科研复核保留每轮有界结果，以及调用前实际可见的上下文/反馈。这部分是磁盘实验记录，不反复全部塞回模型。

## 三个主指标

完整定义、公式和审计规则见 [METRICS.md](METRICS.md)。

| 指标 | 本项目口径 |
|---|---|
| 任务成功率 | 固定题单中独立评测通过题数 / 计划题数；模型提交和局部测试通过不算成功 |
| 平均交互轮次 | 固定题单上每题策略模型响应轮次数的均值，包含提交轮、格式错误轮；网络重试另计 |
| 工具调用冗余率 | 语境审计认定可避免的工具调用次数 / 全部工具调用尝试数；不是命令机械重复率 |

未测完、未审完不会伪造完整值。报告给出覆盖率、未判定数量和上下界；主指标 `null` 意味着证据尚不足，**不是 0**。

```powershell
.\hai.ps1 summary --run .\runs\task-001-hai
.\hai.ps1 audit-template --run .\runs\task-001-hai --out .\audit-task-001.json
# 按 METRICS.md 审核 label/category/reason/evidence_call_ids 等字段后：
.\hai.ps1 summary --run .\runs\task-001-hai --audit .\audit-task-001.json
```

审计是离线工作，不影响 Agent 决策，也不会自动调用付费模型。审计工具可以识别“不同命令重复查同一事实”，也允许“相同命令的合理复测”标为非冗余；它并不声称用简单规则全自动识别语义冗余。

## 对接官方评测

SWE：导出标准预测 JSONL，再交给你已有的官方评测流程。此命令只导出一题，不启动评测：

```powershell
.\hai.ps1 export-swe --run .\runs\task-001-hai --out .\task-001-prediction.jsonl
```

Terminal：外部 harness 等 `run` 返回后，在对应的任务环境中执行独立 verifier。`terminal-submission.json` 不是环境快照，只绑定本次提交；运行目录被复制后不能凭它重建服务、数据库或整个容器。

把实际官方结果规范化成 `examples/evaluation.json` 的结构，填入 run/task/artifact 标识和原始报告 SHA256，再显式导入：

```powershell
.\hai.ps1 attach-evaluation --run .\runs\task-001-hai --report .\official-normalized.json
.\hai.ps1 compare --manifest .\paired-manifest.json --out .\comparison.json
```

导入器校验实际提交文件、run/task/artifact 标识及原始报告摘要，并按 `source_format` 解析原始结果，与规范化 `success` 核对。已支持 `swe-instance-v1`（题号下的 `resolved`）和 `swe-summary-v1`（通过/未通过题号集合），基于本机已有官方报告结构测试；`fixture-reward-v1` 仅供显式的自定义验证器/离线测试，必须有相同 task_id 和二值 reward，不代表官方成绩。原始报告复制到运行目录，移动结果目录不会丢失依据。其他格式包括尚未接入的 Harbor 原始报告明确拒绝，不能只填一个布尔值蒙混导入。

报告解析和哈希不等于认证报告生产者，仍需可信外部 harness 将本次产物与评测环境绑定；不能拿模型自评冒充独立结果。完整报告尚未导入时，`success` 保持未知。

## 调度器和后台进程

`run` 退出码：0 为模型提交（不代表测试成功），3 为预算停止，4 为 API 错误，5 为基础设施错误，130 为中断，2 为输入/配置错误。详细原因保存在 result.json。不要把所有非零退出都自动重跑；重试应遵守冻结实验协议。

正常启动命令退出时，不因后台子进程持有 stdout/stderr 就误杀其进程组；反馈标记 `background_output_open`，输出捕获保持有界。超时命令仍终止进程树。**外部任务容器必须在 verifier 完成后销毁**；本地执行器不承诺追踪所有脱离父进程的服务，特别是 Windows。本工程仍不是容器生命周期管理器。

0.2.0 的协议为 `hai-v2`，记录源码摘要，配对汇总拒绝混用不同协议/源码。修复前后的运行不要当作同一冻结版本混算；指标数学定义未改。

比较命令检查已提供运行的模型、端点和预算一致性，检查同题题面/基准提交/声明环境相符，并拒绝混入题单外任务或重复运行。它无法仅靠日志证明两台机器资源完全一致；环境镜像、隐藏测试隔离、调用顺序随机化和资源配额仍须在实验设计中固定。

## 运行与数据保障

- 单题总墙钟期限传给 API、命令及补丁 Git 操作；API 用独立请求进程处理，达到绝对上限即可终止，不因网络保活无限延长。进程清理有少量额外开销，文件系统扫描是有界尽力而非实时系统保证。
- 命令输出用有界流缓冲；超时终止进程树。Linux 利用进程组；Windows 对已经脱离父进程的后台进程不提供完整隔离保证，真实长期实验推荐 Linux 容器。
- API 只做有限网络/限流/服务器错误重试，鉴权错误不反复重试；重试可能已产生提供方费用，usage 缺失明确计入覆盖率缺口。
- 只有完整 JSON 决策可执行；拒绝从被截断的响应中“抢救”出半条命令。
- 每次运行必须是新目录，追加事件有哈希链、结束报告绑定 trace；不自动续跑、不重复启动、不删除旧结果。
- 结果和进度原子写入；`progress.json` 是最近一次命令结束检查点，不是高频存活心跳。本工程不附带常驻巡检或自动重启任务。
- 脱敏覆盖已知控制器 Key，不是所有潜在秘密的通用检测；请勿在题面、任务文件或命令里放入个人凭据。

来源取舍见 [V14_REUSE.md](V14_REUSE.md)。本实现是推理时 Agent 与记忆基础设施，**尚不包含强化学习训练**。离线测试通过不代表已经优于 Raw。
