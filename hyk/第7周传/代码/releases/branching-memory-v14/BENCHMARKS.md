# BestFGS 评测运行说明

所有入口只运行桌面 `BestFGS`，不会启动或修改 `Explore_priority`、`Exploit_priority` 或 `plore_ploit`。

## 数据冻结与抽样

| 入口 | 开发集抽样 | 固定清单 |
| --- | --- | --- |
| `run_terminal_bench_tenth.py` | 排除冻结 9 题后随机、不放回抽 1/10 | `benchmark_results/terminal-bench/dev-tenth-selection.json` |
| `run_terminal_bench_2random_tasks.py` | 排除冻结 9 题后随机、不放回抽 N 题，默认2 | `benchmark_results/terminal-bench/dev-N-selection.json` |
| `run_swebench_tenth.py` | 排除冻结 50 题后随机、不放回抽 1/10 | `benchmark_results/swebench/dev-tenth-selection.json` |
| `run_swebench_2random_tasks.py` | 排除冻结 50 题后随机、不放回抽 N 题，默认2 | `benchmark_results/swebench/dev-N-selection.json` |

第一次运行会保存 seed、题目 ID 与顺序、开发池指纹、冻结清单指纹和内容 SHA256。以后同一路径直接复用；seed 冲突或文件被修改会报错，不会覆盖。固定的是题目与顺序，不是模型输出或远端镜像内容。

## PowerShell 命令

```powershell
cd C:\Users\54177\Desktop\BestFGS
```

先只检查抽样，不调用模型、不启动评测容器：

```powershell
python .\run_terminal_bench_tenth.py --provider deepseek --sample-seed 20260904 --dry-run
python .\run_terminal_bench_2random_tasks.py --provider deepseek --sample-size 2 --sample-seed 20260904 --dry-run
python .\run_swebench_tenth.py --provider deepseek --sample-seed 20260904 --dry-run
python .\run_swebench_2random_tasks.py --provider deepseek --sample-size 2 --sample-seed 20260904 --dry-run
```

正式运行四组开发评测：

```powershell
python .\run_terminal_bench_tenth.py --provider deepseek --sample-seed 20260904 --max-iterations 24 --max-tool-calls 80 --budget-multiplier 1 --base-children-per-node 3 --max-children-per-node 6 --n-concurrent 1 --max-retries 0
python .\run_terminal_bench_2random_tasks.py --provider deepseek --sample-size 2 --sample-seed 20260904 --max-iterations 24 --max-tool-calls 80 --budget-multiplier 1 --base-children-per-node 3 --max-children-per-node 6 --n-concurrent 1 --max-retries 0
python .\run_swebench_tenth.py --provider deepseek --sample-seed 20260904 --max-iterations 24 --max-tool-calls 80 --budget-multiplier 1 --base-children-per-node 3 --max-children-per-node 6 --max-workers 1
python .\run_swebench_2random_tasks.py --provider deepseek --sample-size 2 --sample-seed 20260904 --max-iterations 24 --max-tool-calls 80 --budget-multiplier 1 --base-children-per-node 3 --max-children-per-node 6 --max-workers 1
```

这些正式命令会消耗 API。两个窗口并行运行还会叠加 API、内存与 Docker 压力。脚本读取已有 `DEEPSEEK_API_KEY`，不应把密钥写进命令行。

正式运行前会先验证 Windows Docker、WSL 中的 Docker 以及对应官方 harness；预检失败时不会拉取镜像，也不会调用模型。仅在明确知道环境可用时才使用 `--skip-preflight`。

Terminal-Bench 可用 `--attempts N` 对每题做 N 次独立尝试，脚本会转成当前 Harbor 的 `--n-attempts`。默认是 1；它会近似按 N 倍增加 API 消耗，因此小规模调试不要提高。

## 预算与停止

基础预算统一为 24 轮 / 80 次工具，难题按题面复杂度调度到 33 / 108，简单题可降至 22 / 72。`--budget-multiplier 1` 关闭额外续算；不要沿用旧实验的 4 倍参数。一次搜索迭代可能包含多个模型请求，所以轮次不是金额上限。

SWE 的 `--max-workers` 现在同时控制 Agent 与官方 harness 并发；Agent 侧最多并发 2 题，默认值也是 2。两个独立容器会真实同时运行，实时日志以 `[SWE 题号/总数 实例ID]` 开头；结果文件仍由主线程按冻结清单顺序写入。

真实 `verified_success` 后立即停止。没有有效动作、复验预留被触达、硬预算耗尽、API/环境异常或外层超时也会停止；算法不会保证每题一定成功。

## 输出指标

终端与摘要文件报告：

- 官方通过数、通过率、异常数；
- 全部有效任务及内部验证成功任务的平均交互轮次；
- 最终语义覆盖率、有效探索比例、知识复用率、工具调用冗余率；
- RE-TRAC经验漏斗（两类规则生成、召回、选择、入队、执行、生效，Recommend全局利用优先，Avoid规避/精确阻止/兜底）；
- `search_algorithm`、每轮求解压力及完整优先级分解。

内部 `verified_success` 不等于 SWE/Terminal 官方 verifier 通过。平均值只纳入有记录的样本，缺失项不按 0 填充；成功率与全体平均轮次必须一起看。

SWE 结果位于 `benchmark_results/swebench/`，包括 `selection-*`、`run-manifest-*`、`predictions-*`、`agent-results-*`、`interaction-summary-*` 和 `official-report-*`。Terminal 结果位于 WSL 的 `/home/research/benchmark-runs/terminal-bench/jobs/<job-name>/`，运行前清单另存于 `/home/research/benchmark-runs/terminal-bench/manifests/`。清单记录题目、模型、Judge、预算、搜索参数、代码指纹及运行环境版本，但不记录 API Key。

SWE 中断后可使用原运行名恢复，例如：

```powershell
python .\run_swebench_tenth.py --provider deepseek --run-id best-fgs-swe-tenth-实际时间戳 --resume --max-iterations 24 --max-tool-calls 80 --budget-multiplier 1
```

恢复只跳过已经完整执行的实例；可重试错误或仅有 checkpoint 的实例会继续运行，并保留旧的非空补丁。若模型、Judge、预算、搜索参数或代码指纹变化，脚本会拒绝沿用同一 `run-id`，避免形成不可辨认的混合实验；确有需要时可显式添加 `--allow-resume-config-drift`。冻结入口 `run_terminal_bench_frozen_test.py` 与 `run_swebench_frozen_test.py` 只在最终评测时使用。

## 实现参考

- [SWE-bench 官方 harness](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/run_evaluation.py)：逐实例报告、已完成结果复用、预测 ID/空补丁检查；
- [OpenHands benchmark runner](https://github.com/OpenHands/benchmarks/blob/main/benchmarks/swebench/run_infer.py)：结构化运行元数据、中断时保留非空补丁；
- [Harbor 结果结构与 Viewer](https://github.com/harbor-framework/harbor/blob/main/docs/content/docs/run-jobs/run-evals.mdx)：job/trial 配置、轨迹、verifier 产物、耗时与 token 统计；
- [Terminal-Bench 官方运行示例](https://github.com/harbor-framework/docs/blob/main/examples/terminal-bench.mdx)：任务过滤、超时、并发及多次尝试。

## 离线代码测试

```powershell
$env:PYTHONPATH = "$PWD\src"
python -B -m unittest discover -s tests -v
```

这不会调用模型 API，也不能替代真实 benchmark。
