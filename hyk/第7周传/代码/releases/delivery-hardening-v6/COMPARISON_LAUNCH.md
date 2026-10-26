# 2026-09-18 午夜前启动的配对实验

用户授权：环境实在准备失败时可以换题，凑齐 100 题，两组使用相同清单，不抽冻结测试集。

## 选择规则（在解题之前固定）

1. 保留原计划中截至新清单冻结时已准备成功的题目。
2. 从 Verified 的同一缓存版本抽取候补，排除原 100 题、原排除的历史题与冻结测试集。
3. 为满足截止时间，候选只允许使用已成功准备题目相同的依赖缓存配方；该筛选仅依赖环境，不依赖模型得分。
4. 246 个符合环境条件的候选按固定种子 `2026091802` 随机抽取 40 个形成有序候补池。按该顺序准备，每题一次；下载有有限重试。
5. 总共凑够 100 个可用环境后，按候补池顺序补上未就绪原题的位置，冻结新题单和换题审计。原题单和失败日志不覆盖。

这是**环境可运行性条件下的开发样本**，不是完整 Verified，也不是未经筛选的随机 100 题。换题会改变项目分布，报告时须披露新清单、种子、排除条件、换出原因和项目数量。相同的新清单只能保证两种方法在该样本上的配对公平，不能消除样本选择偏差。

## 自动链路

`prepare_swe_comparison.py`：候补环境准备 → 新题单冻结 → 全部 100 题种子/依赖指纹检查 → `run_comparison.py` 顺序执行两组 200 次任务。

`--start-comparison` 明确允许准备完成后产生 DeepSeek API 费用。不设置该参数则只准备和检查。若到指定 `--deadline` 还没有通过预检，不会擅自删题或超时启动。第一次正式启动后不会因为过午夜而中断实验。

原来的修复任务与候补任务使用不同目录；候补只读取旧缓存及 ready 清单，不覆盖旧环境。新项目部署到 `/mnt/lizh639/BestFGS-compare-v3`。

```bash
/mnt/lizh639/envs/bestfgs/bin/python -u prepare_swe_comparison.py \
  --source-root /mnt/lizh639/bestfgs-runs/swe100-v1 \
  --reserve-plan examples/swe100-reserve-plan.json \
  --root /mnt/lizh639/bestfgs-runs/swe100-reserve-v1 \
  --output-root /mnt/lizh639/bestfgs-runs/swe100-paired-v2 \
  --deadline 2026-09-19T00:00:00+08:00 --start-comparison
```

固定新题单位于候补根目录 `frozen/task-plan.json`，换题审计在 `frozen/replacement-audit.json`。Agent 和 raw 结果分别在新结果根目录的 `bestfgs/`、`raw/`。保持同一个 v3 代码和协议，不混入此前单题调试的成绩。官方 Docker harness 评测仍在本机按 `BASELINE_COMPARISON.md` 执行。
