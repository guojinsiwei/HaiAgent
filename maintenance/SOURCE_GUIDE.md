# 源码索引（2026-10-26）

本次将本地研究工程按原目录结构归档，保留模块间相对路径。目录归属表示工程来源；三位成员的协作分工沿用根目录说明。历史实验目录中的 README 和验证报告只描述当时版本。

| 工程 | 入口 / 位置 | 用途 |
| --- | --- | --- |
| HAIAgent | `projects/HAIAgent` | Python 单路径 CLI Agent，0.8.2 |
| KZ 原生版 | `projects/kz-native-mechanism-sync-20261019/native/solve.py` | 2026-10-19 机制同步版，保留 Python 执行框架 |
| KZDSH 基线 | `projects/kz-dsh-baseline-share-20261018` | 0.3.0 冻结基线 |
| KZDSH exploration-v2 | `projects/kz-dsh-exploration-v2-20261018/candidate` | 改进探索触发、测量与结果利用 |
| HLD 初始语义规划版 | `projects/HLD` | 0.4.0-semantic.2，本地独立候选 |
| HLD v8 | `projects/tb2-hld-mechanism-ab10-20261022/candidate` | 既有实验使用的 v8 源码快照 |
| HLD 效率候选 v9.1 | `projects/hld-efficiency-v9-repair-20261023/candidate` | 独立效率修复候选，效果须以正式实验为准 |
| SUZ | `projects/SUZ`、`projects/SUZ-repair1` 至 `SUZ-repair5` | 桌面视觉控制器及独立工程修复版 |
| SUZ 多基准适配 | `projects/suz-multibench-20261026` | WebArena / AndroidWorld 调度、适配与修复源码 |
| Recuris DSH | `projects/recuris-dsh` | 冻结机制的 DSH 适配；不等同于完整论文复现 |
| TACO DSH | `projects/taco-dsh` | 题内规则演化适配；不启用跨题全局演化 |
| 共同基线 | `projects/dsh-baselines` | DSH 宿主、共同配置与离线测试 |
| 组件 | `components/` | 上下文、通知、Recuris、TACO、LATS 源码及参考 |
| 历史方法 | `BestFGS*`、`plore_ploit`、`releases/` | 原始工程及各阶段独立快照 |
| 实验工程 | `projects/tb2-*`、`longcli-*`、`swepro-*` 等 | 环境准备、预算调度、评分、重试与汇总脚本 |

## 使用与验证

先选择一个明确版本，再阅读该目录的依赖和运行说明。Python 工程与 Node 工程分别安装依赖；DSH 工程固定的宿主版本以各自 `package.json` / 锁文件为准。多数 Node 工程要求 Node.js 24。

```sh
python maintenance/verify_snapshot.py
cd projects/HAIAgent
PYTHONPATH=src python -m unittest discover -s tests -v
```

Windows 下 HAIAgent 可直接执行 `projects/HAIAgent/test.ps1`。本次离线检查记录见 `VALIDATION.md`。历史源码保留已知限制，不把源码入库表述为所有 benchmark 均已通过。

## 快照边界

- 保留源代码、测试、工程配置、依赖锁、许可证和项目说明。
- 本地凭据、依赖环境、运行缓存、模型原始输出、截图、压缩部署包和大体积外部数据留在原环境。
- 部分历史运行脚本引用原服务器目录或未收录的实验记录，使用前须按目标环境调整路径并准备外部资源。
- 当前正在推进的实验可能继续产生更新；本次文件哈希定义本次入库版本。
- 第三方代码保留原许可证及来源，不改变署名，不将第三方工作记作团队原创。
- `maintenance/source-manifest.json` 记录每个导入文件的 SHA-256；后续正常开发修改文件后，旧清单仅用于追溯此次导入。
- 多个第三方工程原含自己的 CI 文件，根目录未启用这些历史工作流；入库不启动模型或部署任务。

霍彦凯已提交的 `huoyankai/week6-week7` 分支和 PR #1 保持独立，后续按团队评审流程处理。

## 第三方来源

- `components/TACO`：https://github.com/multimodal-art-projection/TACO ，本地基准提交 `2b048988e77ea67e6165450c97ebe66ce23a033f`。
- `components/LanguageAgentTreeSearch`：https://github.com/andyz245/LanguageAgentTreeSearch ，本地基准提交 `853d81614607dd27433faf17c7b0a7d660f95d22`。
- SUZ 中 OpenCUA 文件来自 https://github.com/xlang-ai/OSWorld ，上游版本和逐文件哈希见各工程的 `upstream-lock.json`。
- Recuris 与 DSH 适配的来源和机制差异见各工程 README、`source-lock.json` 以及 `vendor/` 中的许可证。

上游提交标识用于来源追溯；本地适配可能带有改动，实际入库字节以本仓库的源码清单为准。
