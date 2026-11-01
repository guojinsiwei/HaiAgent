# Recuris × LongCLI-Bench

根据用户提供的 **Recursive Experiential–Working Memory Evolution for Long-Horizon Agent Harnesses**（`recuris.pdf`，arXiv:2608.24876v1）实现 Recuris 的四组件记忆、任务内执行与任务外适配，并接入 [LongCLI-Bench](https://github.com/finyorko/longcli-bench) 原生 Agent 接口。

**只交付实现、离线测试和运行说明；没有调用真实模型、没有启动 Docker 或运行基准实验，没有成功率结果。** 项目可独立转交，不需要工作区里的 `reflexion` 或 `retrac`。直接发送 `dist/recuris-handoff.zip`，解压后按本说明安装。

这是一份基于论文并核对作者源码的 **LongCLI 迁移实现**，不是原作者 Terminal-Bench 2.1/Harbor 实验逐行移植。工作记忆检查、模型交互协议、JSON 记忆格式和跨任务 gate 有明确的工程差异，见 [论文与源码对照](docs/reproduction.md)。

## 接手者安装

推荐 Linux / WSL2，Python 3.12+、Docker、Docker Compose 和 uv。下面命令由接手者执行，本次未执行。

```bash
git clone https://github.com/finyorko/longcli-bench.git
cd longcli-bench
git checkout 2015f37b5c458f2562354de6b415e9182c91af64
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uv pip install -e /absolute/path/to/recuris

cd longcli_dockerImage
docker build -f Dockerfile.make-pytest-base -t tb/make-pytest:v0 .
docker build -f Dockerfile.c-env-base -t tb/c-env:v0 .
cd ..

export DEEPSEEK_API_KEY='由运行者设置'
export DEEPSEEK_MODEL='账号可用的模型ID'
# 可选兼容端点；默认 https://api.deepseek.com
# export DEEPSEEK_BASE_URL='https://your-provider.example/v1'

python -m recuris doctor --model "$DEEPSEEK_MODEL"
```

必须安装指定的 **LongCLI 官方仓库**，仅安装 PyPI 的 `terminal-bench` 不能确认评分接口一致。这个项目与作者原仓库都使用 Python 包名 `recuris`，请放在独立环境中，**不要同时安装两者**。`docs/upstream/` 是只读参考快照，不需要安装。

`doctor` 不联网，只检查配置、记忆和适配器导入，不验证容器或真实模型端点。完整接口说明见 [LongCLI 接口](docs/longcli-contract.md)。

## 选择初始记忆

提供两种未经过学习的起点：

```bash
# 将作者官方 task-neutral closed-loop 技能转换为本适配器的 JSON 格式
python -m recuris seed --profile terminal --output /absolute/path/to/terminal-seed.json

# 可选：完全空的 E，用于无经验起点/消融
python -m recuris seed --profile neutral --output /absolute/path/to/neutral-memory.json
```

`terminal` 包含作者的一条“检查—最小修改—实际验证”通用技能，来源与 Apache-2.0 许可保存在 `docs/upstream/`；W/C 是本适配器的终端实现。**不提供声称已完成学习的 LongCLI 技能。** 不指定记忆文件时默认使用 `neutral`，其 `E=[]`。开展论文终端模式的对照时，两边应显式传入相同的 `terminal-seed.json`。

## 单次 LongCLI 运行

```bash
export RECURIS_MEMORY_PATH='/absolute/path/to/terminal-seed.json'
bash /absolute/path/to/recuris/scripts/run_longcli.sh \
  /absolute/path/to/longcli-bench 61810_cow \
  --output-path /absolute/path/to/runs_recuris
```

脚本第二个参数必须是一个已有任务 ID；全数据集需显式用 `--all`。脚本只组装官方 `tb run`，不下载数据或安装环境。直接调用等价形式：

```bash
tb run \
  --agent-import-path recuris.longcli:RecurisAgent \
  --model "$DEEPSEEK_MODEL" \
  --dataset-path /absolute/path/to/longcli-bench/tasks_long_cli \
  --task-id 61810_cow \
  --n-attempts 1 --give-test-output 1 --n-concurrent 1 \
  --agent-kwarg memory_path=/absolute/path/to/terminal-seed.json \
  --agent-kwarg max_steps=200 \
  --agent-kwarg max_total_seconds=3600 \
  --global-agent-timeout-sec 3900
```

不要同时传 `--agent`。这条命令只执行一次冻结记忆的 attempt；**不会在代理内部用模型自评模拟官方反馈重试**。最终 F2P/P2P 和任务成功由上游 harness 评分，代理日志里的 `official_success` 固定为 `null`。

## 论文终端模式：任务内适配 TTA

使用独立外层运行器，每次启动新的官方 attempt，最多 4 次，官方首次成功即停。失败后 Meta-Agent 只接收原任务、代理可见轨迹和一个失败 bit，只能改 `E`；下一次在新 attempt 中加载更新后的记忆。隐藏测试和预期答案不进入 Meta-Agent。

```bash
python -m recuris tta \
  --benchmark-root /absolute/path/to/longcli-bench \
  --task-id 61810_cow \
  --model "$DEEPSEEK_MODEL" \
  --memory /absolute/path/to/terminal-seed.json \
  --mode adaptation --attempts 4 \
  --output-dir /absolute/path/to/runs/recuris-tta-61810
```

每次 `--output-dir` 必须是新目录，避免覆盖。可用重复的 `--agent-kwarg max_steps=...` 等调整执行预算。默认 policy 温度为 0；不支持该参数的端点可传 `--temperature null`。Meta-Agent 默认用同一个模型，可通过 `--meta-model` 单独固定选择；其额外调用和用量写入候选日志。

对应的预算匹配对照为 `--mode frozen --attempts 4`，每次都使用不变的 seed，不调用 Meta-Agent。为了像论文一样共享首次轨迹，先做一次公共首轮，再由两组只读复用：

```bash
python -m recuris tta --benchmark-root /path/to/longcli-bench \
  --task-id 61810_cow --model "$DEEPSEEK_MODEL" --memory /path/to/terminal-seed.json \
  --mode frozen --attempts 1 --output-dir /path/to/runs/shared-first

python -m recuris tta --benchmark-root /path/to/longcli-bench \
  --task-id 61810_cow --model "$DEEPSEEK_MODEL" --memory /path/to/terminal-seed.json \
  --mode frozen --attempts 4 --seed-attempt-dir /path/to/runs/shared-first/attempt-01 \
  --output-dir /path/to/runs/frozen-four

python -m recuris tta --benchmark-root /path/to/longcli-bench \
  --task-id 61810_cow --model "$DEEPSEEK_MODEL" --memory /path/to/terminal-seed.json \
  --mode adaptation --attempts 4 --seed-attempt-dir /path/to/runs/shared-first/attempt-01 \
  --output-dir /path/to/runs/adapted-four
```

共享前会核对任务、模型、端点、预算、代码、记忆以及日志文件哈希；配置不符会停止。`null` 评分、缺失结果、模型/测试故障不会转换成官方失败样本。结果为 `incomplete` 时应修复原因，而不是把它计作正常失败或继续学习。哈希用于检测文件变更，不是防恶意伪造的签名。

`tta` 为每个指定任务独立维护记忆。不同任务不自动共享它。四次预算内成功率、固定记忆上四次完整独立采样的 avg@4、官方 `--n-attempts` 是不同的统计设置，不能混用。

## 跨任务记忆进化

还提供论文 §2.3 的四组件候选生成与确定性准入接口，适合需要做跨任务扩展的运行者：

1. 预先冻结互斥的 evolve/dev/test 划分及重复编号。
2. 在 evolve 任务的已完成官方失败上运行 `recuris propose`，生成归因及限定组件的候选。
3. 用固定记忆模式分别评测原记忆、候选记忆的源任务和全部 dev/anchor 任务。
4. `recuris admit` 从有校验清单的官方 attempt 读取配对结果；通过则写候选，拒绝则写原记忆。下一轮以该输出继续。

```bash
python -m recuris propose --mode cross_task \
  --attempt-dir /path/to/evolve-run/attempt-01 --model "$DEEPSEEK_MODEL" \
  --output-dir /path/to/candidate-01

python -m recuris admit \
  --base-memory /path/to/base-memory.json \
  --candidate /path/to/candidate-01/candidate.json \
  --evaluations /path/to/evaluations.json --split /path/to/frozen-split.json \
  --output-dir /path/to/admission-01
```

完整 JSON 格式、配对检查和 gate 条件见 [进化接口](docs/evolution.md)。跨任务 gate 是本实现明确选择的“源失败修复、anchor 不回退、dev 均值不下降”严格规则，**不是论文作者所有 gate 入口的统一复刻**。TTA 不使用这个 dev gate；两种模式分别记录。

## 单次执行机制与默认预算

`W` 从任务建立带验证命令的目标；`rho` 在事件边界调用 `E`；Actor 执行动作；W 提出状态变更；`C` 根据真实检查回执判定；固定内核只提交受支持的变更。每步完整记录 `w_before, skills, action, observation, proposal, checker, w_after`。

公开检查在任务终端中的子 bash 执行，使用随机 BEGIN/END 标记获取退出码，并排除命令回显。普通命令、模型自称、技能注入、假 ID、旧状态回执和未完成检查都不能把目标改为 `done`。非空终端输入会保守地使旧完成状态失效；后续需重新检查。**退出码 0 只证明配置的公开检查通过，并不证明检查覆盖了完整任务或官方测试。**

| 配置 | 默认 | 含义 |
|---|---:|---|
| `max_steps` | 200 | 单次 attempt 的 Actor 步数上限 |
| `max_tool_calls` | 400 | 终端输入与轮询总上限 |
| `max_model_calls` | 450 | 初始化、Actor、W 更新及格式修复总调用数 |
| `max_total_seconds` | 3600 | 单次代理内部时间上限 |
| `max_consecutive_tool_errors` | 10 | 连续已观测非零验证退出码上限；普通交互 shell 无可靠退出码时不猜测 |
| `max_context_chars` | 120000 | 输入字符限制，不是 token 窗口 |
| `max_observation_chars` | 20000 | 供模型查看的单次输出上限，显式头尾截断 |
| `max_command_duration` | 120 | 单次终端等待秒数 |
| `max_verify_seconds` | 120 | 一次 verification 的内部等待上限；未结束可继续轮询 |
| `max_parse_attempts` | 2 | JSON 响应总尝试次数 |
| `history_turns` | 12 | Actor 保留的近期行动/观察对；完整 trace 另外保存 |

记忆里的 `W.max_goals` 默认为 8，`rho.trigger=first_turn`；也支持受限的事件/检索变体供跨任务 patch 使用。改用额外事件后应在实验设置中注明。不会动态执行技能里的 Python 或让候选重写内核。

模型通用参数还包括 `base_url`、`api_key_env`、`timeout_seconds=120`、`max_attempts=3`、`max_output_tokens=4096`、可选 `top_p`、`reasoning_effort` 与 `extra_body`。密钥仅从指定环境变量读取。兼容服务配置详情见 [接口说明](docs/longcli-contract.md)。

## 日志、检查与文件

单次代理在 `<logging_dir>/recuris/<唯一ID>/` 保存 `context.json`、`memory.json`、`events.jsonl`、`trace.json`、`result.json`。TTA 外层保存每个 attempt 的官方结果位置、哈希清单、模型/配置来源、候选、最终记忆和 `summary.json`。所有模型角色都统计 API 已报告的 token；未知用量不推测。日志脱敏不是完整数据匿名化。

Actor 审计快照与进程输出会脱敏；需要核验摘要的候选、attempt 清单和外层记忆按原值保存，不能把它们当成已匿名化的日志。模型凭据通过环境变量提供；外层配置拒绝凭据参数，环境端点仅保存身份摘要。重新使用记忆应选择外层 `memory.json` 或 `final-memory.json`，而非脱敏后的 Actor 审计快照。

离线检查命令，不需要模型密钥或 Docker：

```bash
cd /absolute/path/to/recuris
python -m pip install -e '.[test]'
python -m pytest -q --basetemp .test-tmp-local
python -m recuris --help
python -m recuris config
```

具体验证记录见 [validation.md](docs/validation.md)。真实模型和 Docker 端到端运行留给接手者。

转交包位于 `dist/recuris-handoff.zip`，压缩包校验值在 `dist/SHA256SUMS`，逐文件清单同时保存在包内。修改代码后运行 `python scripts/build_handoff.py` 可重新生成；脚本不触发模型或 benchmark。

| 文件 | 用途 |
|---|---|
| `src/recuris/longcli.py` | 原生 LongCLI Agent 与 tmux 桥接 |
| `src/recuris/engine.py`、`working.py` | 单次执行、回执、W 提议与确定性提交 |
| `src/recuris/memory.py`、`skills/` | 四组件 JSON 记忆与两个初始 profile |
| `src/recuris/evolution.py`、`admission.py` | 固定 Meta-Agent、组件限定 patch、评分准入 |
| `src/recuris/tta.py` | 官方独立 attempts、失败 bit 隔离、共享首次轨迹 |
| `scripts/run_longcli.sh` | 单次原生运行入口 |
| `docs/upstream/`、`vendor-contracts/` | 固定提交的参考源码、接口、校验值和原许可证 |

本项目不包含任务数据、隐藏测试、模型密钥或已跑出的学习结果。
