# 转 CV 前的 CLI / 语义规划源码补齐（2026-10-31）

本次核对本地 CLI 阶段源码与共享仓库 main。HLD、KZ、KZDSH、HAIAgent、Recuris/TACO 适配及标准 releases 下的历史版本已在前次导入中收录；本次补齐此前位于早期工作副本中的源码、测试、依赖声明、评测脚本和说明。

新增文件位于 `releases/pre-cv-archive-20261031/`，其下保留原工作副本名称和内部相对路径。目录中的 `.codex-bestfgs-*` 名称来自本地历史工作副本，用于版本追溯。它们是独立历史快照，不应当作当前生产入口。每个完整工程从自己的目录运行；部分早期备份只包含当时修改的文件。

## 本次补齐

| 原工作副本 | 文件数 |
| --- | ---: |
| `.codex-bestfgs-backup-20260915` | 8 |
| `.codex-bestfgs-baseline` | 77 |
| `.codex-bestfgs-batch` | 70 |
| `.codex-bestfgs-launch` | 85 |
| `.codex-bestfgs-nojudge` | 74 |
| `.codex-bestfgs-notebook` | 62 |
| `.codex-bestfgs-prepfix` | 79 |
| `.codex-bestfgs-reduction` | 54 |
| `.codex-bestfgs-refactor` | 54 |
| `official-submission-v3` | 2 |
| `review_gaidong` | 1 |

## 代码边界与验证

用户确认此次仅覆盖 CLI / 语义规划阶段。SUZ、KaM、YZ 及其他视觉 GUI 工程未加入此次改动。凭据、虚拟环境、依赖、运行日志、模型输出、评测结果与缓存未纳入本次补齐。

现有常规 CLI 目录的差异核对中，KZ 原生版两处测试仍保留前次入库的父目录创建修复，不用本地旧测试回退。项目目录中的视觉修复脚本也未纳入。

`pre-cv-manifest-20261031.json` 保存新文件的原路径、仓库路径和 SHA-256；`source-manifest.json` 同步追加新文件，可用 `python maintenance/verify_snapshot.py` 校验。新增文件字节与原文件一致。凭据扫描命中的 Retrac 测试仅含固定的测试字符串，用于检查配置和脱敏行为。

本次归档不改写旧算法实现。离线验证及限制见本页后续记录；未运行付费模型或远程 benchmark。

验证结果：新增 566 个文件与源文件、Git 暂存对象的 SHA-256 全部一致；新增 Python 文件均通过语法解析。完整快照校验 15,896 个文件通过。HLD 语义规划 27 项测试、归档 BestFGS 基线 Retrac 24 项测试通过。Retrac 的两项本地 HTTP 测试首次受沙箱网络限制，解除该限制后完整重跑通过。历史快照未逐版本运行全部测试。
