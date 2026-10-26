# v15 验证记录

2026-09-26，本地 Windows，全部使用模拟模型、模拟 CLI 或测试 HTTP 服务，未调用付费 API。

- 最终全量回归：651 项，640 通过、11 跳过、0 失败（192.706 秒）。
- 新增协作专项：14 项全部通过。
- CLI `python -m bestfgs --help` 正常。
- 最终完整输出：`validation-v15-final.log`。
- 首轮日志 `validation-v15.log` 保留供审计；旧模块白名单与 CLI mock 已更新以覆盖新入口。
  首轮断点续跑用例失败后，在 v14/v15 独立复查均通过；停止编辑后最终全量复查通过。

与源 v14 按 SHA-256 核对，以下文件完全相同：best_first.py、best_first_runtime.py、
environment.py、rules.py、experience.py、micro_experience.py、blocking_memory.py、
evidence_memory.py、evidence_runtime.py、priority.py、semantic.py、models.py、submission.py、
metrics.py、experiment_metrics.py、redundancy.py、raw_baseline.py。

行为验证不等于模型效果验证；尚未部署或开始新实验。新角色模型的真实费用与质量未测。
