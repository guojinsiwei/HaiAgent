# plore_ploit 评测运行说明

这两个入口只运行 `plore_ploit`，不启动或修改 `Explore_priority`、`Exploit_priority`。继续复用原项目的 Docker / WSL / Harbor / SWE-bench 官方评测流程。

## 抽样与冻结

| 入口 | 抽样规则 | 原冻结集处理 | 默认开发题清单 |
| --- | --- | --- | --- |
| `run_terminal_bench_tenth.py` | 从非冻结开发池均匀、不放回抽取 1/10，向上取整 | 排除原有 9 题 | `benchmark_results/terminal-bench/dev-tenth-selection.json` |
| `run_swebench_18tasks.py` | 从非冻结开发池均匀、不放回抽取 18 题 | 排除原有 50 题 | `benchmark_results/swebench/dev18-selection.json` |

原 `benchmark_splits/frozen_test_set_v1.json` 及 SHA256 文件保持不变，且与两个原项目一致。按该清单记录的全集规模，Terminal 为 `ceil((89 - 9) × 0.1) = 8` 题，SWE 为 `500 - 50 = 450` 道开发题中抽 18 道。Terminal 的 1/10 分母是**开发池**，不是包含冻结题的全集；执行时以实际发现的题数计算。

首次使用一个清单路径时会抽样、保存 seed、题目及顺序、题库规模、开发池 ID 指纹和原冻结清单指纹。后续运行直接读取它，不再抽题。清单附内容 SHA256，意外修改会报错；同一路径指定不同 seed 也会报错，不会覆盖原实验。

固定的是**题目 ID 与顺序**，不是每次模型输出，也没有把远端数据集内容或 Docker 镜像做字节级快照。正式实验仍应固定模型配置及数据/镜像版本。开发抽样可以包含历史做过的开发题；不是仅抽此前从未尝试的题。

## PowerShell：开始运行

沿用之前已经配好的环境：Windows Python 3.11+、Docker Desktop（WSL 集成）、Ubuntu 中的 Harbor，以及 `/home/research/SWE-bench/.venv/bin/python`。模型 API Key 使用已有的 `DEEPSEEK_API_KEY`；本脚本不设置或打印密钥。Windows Python 入口本身只需要标准库，不必重新安装旧项目。

先进入新项目目录：

```powershell
cd C:\Users\54177\Desktop\plore_ploit
```

Terminal-Bench 2（默认每次只并发 1 题）：

```powershell
python .\run_terminal_bench_tenth.py --provider deepseek --sample-seed 20260904 --max-iterations 24 --max-tool-calls 80 --budget-multiplier 4 --base-children-per-node 3 --max-children-per-node 6 --n-concurrent 1
```

SWE-bench Verified（18 题，官方评测并发 1）：

```powershell
python .\run_swebench_18tasks.py --provider deepseek --sample-seed 20260904 --max-iterations 24 --max-tool-calls 80 --budget-multiplier 4 --base-children-per-node 3 --max-children-per-node 6 --max-workers 1
```

可以分别在两个 PowerShell 窗口运行。并行会增加 API、内存和 Docker 负载；资源紧张时顺序运行。两条命令默认各生成唯一运行名，重复运行仍用同一题目清单，但创建新的结果目录/文件。

如模型或 API 地址不沿用默认值，在命令末尾加 `--model 你的模型名 --base-url 你的接口地址`。不要把密钥写入这两个参数。首次初始化清单会使用 WSL 中现有的数据集工具发现题目，可能需要网络；后续复用清单不需要重新发现题目，但正式运行仍可能需要下载任务数据或镜像。

## 仅抽样检查，不消耗模型 API

```powershell
python .\run_terminal_bench_tenth.py --sample-seed 20260904 --dry-run
python .\run_swebench_18tasks.py --sample-seed 20260904 --dry-run
```

`--dry-run` 会保存/校验开发题清单，并显示题目、seed、预算；不调用模型、不启动任务容器或官方评测。去掉 `--dry-run` 后正式运行会使用刚才保存的题目。它不是完全离线操作：清单首次生成时可能联网发现数据集。

如确实需要另一次独立抽样，必须换 seed **和清单路径**，保留旧文件用于复现：

```powershell
python .\run_terminal_bench_tenth.py --sample-seed 20260905 --selection-file .\benchmark_results\terminal-bench\dev-tenth-seed20260905.json --dry-run
python .\run_swebench_18tasks.py --sample-seed 20260905 --selection-file .\benchmark_results\swebench\dev18-seed20260905.json --dry-run
```

正式运行沿用相同的 `--selection-file`。不能按成功率挑选“最好的一组题”作为最终比较；比较不同策略时应使用同一清单和预算，并保留失败、空补丁、异常样本。

## 预算和停止条件

两个新入口默认基础预算均为 24 轮 / 80 次工具调用、弹性硬上限 4 倍，语义树宽 3–6。预算仍按题面复杂度调度：例如复杂题初始为 33/108，最高 132/432；这是上限，不是每道题一定消耗的数量。

得到 `verified_success` 后提前结束并最终复验；无可执行动作、预算耗尽、API/环境异常或外层超时也可能结束。不是无限运行、也不保证成功。Terminal 另受 Harbor 任务超时约束（默认 `--agent-timeout-multiplier 20`）；SWE 的 `--harness-timeout 1800` 是官方测试超时，不是模型搜索的总时间预算。

## 终端指标与结果文件

两个入口均显示题目列表和预算，结束时输出：

- 官方通过数、通过率及异常数；内部 Agent `verified_success` 不冒充官方通过。
- 全部有记录任务的平均交互轮次、内部验证成功任务的平均交互轮次及有效记录数。交互轮次按真实环境转移计数，不把 API 重试次数当作交互轮次。
- 最终语义覆盖率、有效探索比例、知识复用率、工具调用冗余率。按有记录任务做宏平均，每项显示有效记录数，缺失值显示 `N/A`、不按零填充；保持原指标定义，不参与在线策略。

SWE 结果在 `benchmark_results/swebench/`：

- `dev18-selection.json`：默认固定开发题清单。
- `selection-<run-id>.json`：本次运行的题目与抽样清单指纹。
- `predictions-<run-id>.jsonl`、`agent-results-<run-id>.json`：补丁与每题过程/模型用量。
- `interaction-summary-<run-id>.json`：交互轮次与四项指标汇总。
- `official-report-<run-id>.json`：SWE 官方结果。

Terminal 结果在 WSL 的 `/home/research/benchmark-runs/terminal-bench/jobs/<job-name>/`：`result.json` 为官方结果，`interaction-summary.json` 保存轮次、四项指标及所用开发题清单；每个 trial 的 `agent/` 保存过程日志与 Agent 结果。开发题清单另保存在 Windows 项目的 `benchmark_results/terminal-bench/`。

内部成功任务平均轮次不是“官方通过任务平均轮次”。只看这一平均值不能证明效率提升，要同时看端到端通过率与全体有记录任务轮次；两类指标的有效样本数可能不同。

## SWE 中断恢复

将终端显示的原运行名填入 `--run-id`，加上 `--resume`，并保留原清单及参数。例如以下运行名需要换成实际值：

```powershell
python .\run_swebench_18tasks.py --provider deepseek --run-id plore-ploit-swe18-20260904-120000-000000 --resume
```

如果原来用了自定义 `--selection-file` / `--results-dir` / 模型或预算参数，恢复时也要带上。恢复按已保存的预测记录跳过题目，**已有空补丁或失败预测也会跳过**；它不等于重试失败题。不使用 `--resume` 却复用已有运行名会报错以保护结果。Terminal 的这两个入口不提供断点恢复，重复命令是同题的新运行。

## 最终冻结测试入口

`run_terminal_bench_frozen_test.py`（原冻结 9 题）和 `run_swebench_frozen_test.py`（原冻结 50 题）继续保留。开发调参时不要运行，也不要启用 `--allow-frozen-test-set`。当前这次随机 8/18 题属于开发评测，不会替代原最终测试集。

## 离线验证

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

测试覆盖冻结清单校验、排除冻结题、18 题/1⁄10 题数、固定 seed、重复运行复用、篡改和参数冲突拒绝、SWE 模拟执行与恢复、指标汇总。单元测试不调用真实模型或启动评测容器，不代表真实 benchmark 成绩。
