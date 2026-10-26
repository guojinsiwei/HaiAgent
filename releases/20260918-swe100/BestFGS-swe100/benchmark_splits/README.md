# 冻结测试集 v1

`frozen_test_set_v1.json` 是在 2026-09-01 从历史从未运行过的题目中一次性抽取的最终测试集：

- SWE-bench Verified：50 题；
- Terminal-Bench 2：9 题。

开发、调参和消融实验不得运行这些题。普通随机入口会自动排除它们，显式选择时也会拒绝。只有 `run_swebench_frozen_test.py` 和 `run_terminal_bench_frozen_test.py` 可以运行该清单。

该文件由 SHA-256 校验并设置为只读。以后不要修改或覆盖 v1；如果研究方案必须重新划分，只能另建 v2，并保留 v1 和变更原因。
