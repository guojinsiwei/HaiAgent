# 2026-10-26 源码导入验证

此次整理保留项目算法实现，增加根目录导航、忽略规则及逐文件哈希校验。没有启动付费模型、远程部署或 GPU 任务。

| 检查 | 结果 |
| --- | --- |
| Git 暂存内容与源码清单 | 15,330 个源码及配套文件哈希全部一致；无清单外导入文件 |
| HAIAgent：`test.ps1` | 123 项：122 通过、1 跳过 |
| HLD：`node --test tests/semantic-planner.test.mjs tests/semantic-integration.test.mjs` | 27 项通过 |
| SUZ-repair5：`node --test tests/*.test.mjs` | 15 项通过 |
| KZ 原生版：`python -m unittest test_mechanism_parity test_exploration_learning test_exploration_trigger` | 修正路径后 53 项：50 通过、3 失败，与原源码相同；见下文 |

HLD 使用原工作区已安装的固定 DSH 依赖进行检查；其被测源码与导入文件的 SHA-256 一致。HAIAgent、SUZ 和 KZ 在独立导入目录执行检查。

## KZ 已知失败与移植修正

原始工作区和独立快照均复现以下 3 项失败，执行结果为 `infrastructure_error` / `AttributeError`。本次保留算法代码，不将其标记为已修复：

- `test_actual_monitor_hook_starts_exploration_without_faking_failure`
- `test_actual_native_executor_accepts_grounded_receipt_and_counts_roles`
- `test_fabricated_basis_and_coverage_cannot_accept`

独立快照额外发现 `test_exploration_learning.py`、`test_exploration_trigger.py` 创建测试临时目录时未建立父目录。将两处 `mkdir(exist_ok=True)` 改为 `mkdir(parents=True, exist_ok=True)`，使全新克隆可以建立所需目录；生成的 `experiment_records/` 已加入忽略规则。

## 源码与公开提交检查

源码清单逐文件记录 15,330 个导入文件的 SHA-256。上述两处测试路径修正另记原始哈希和修改说明。使用 `python maintenance/verify_snapshot.py` 可重新验证该快照。三个原生工程所需的 `cacert.pem` 已确认为公开 CA 证书包并收录，不含私钥。

扫描排除了 `.env`、密钥文件、安装依赖、缓存、运行目录、压缩包和部分实验报告。测试中保留的伪密钥、公开 benchmark 默认密码、环境变量引用和脱敏测试字符串均用于测试或上游示例；不作为真实凭据使用。

历史发布版、第三方工程和全部 benchmark 未运行完整回归。此记录仅证明列出的检查结果，算法效果以各正式实验的独立评分为准。
