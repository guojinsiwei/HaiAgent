# 第二个 Cube-Studio Notebook

2026-09-18 配置，第二容器 `lizh639-8e64`。不修改第一个容器，不自动启动付费实验。

## 连接

本机 PowerShell：

```powershell
ssh cubestudio_container2
```

第一个连接仍为 `ssh cubestudio_container`。二者经过同一个 `jumpServer`，第二个使用平台提供的端口 `31121`，第一个仍为 `31081`。第二个已授权用户现有公钥，本机私钥不上传。旧 SSH 配置备份位于 `C:\Users\54177\.ssh\config.before-second-notebook-20260918`。

第二容器交互式登录会激活 `/mnt/lizh639/envs/bestfgs`，进入 `/mnt/lizh639/BestFGS-compare-v3`，设置 OMP/OpenBLAS 单线程及无界面 Matplotlib。不会自动调用模型。非交互命令可直接使用 Python 绝对路径。

## 已准备内容

- 两边 cgroup 配额均为 CPU 10 核、内存 16,000,000,000 字节。
- `/mnt/lizh639` 是同一个共享 NFS 工作目录，现有项目与 Conda 环境无需重新上传或克隆。
- 第二容器补齐与第一容器同版本的 12 项系统构建/测试依赖，包括 GCC 构建工具、gfortran、freetype、qhull、Graphviz 等。
- Python 3.11.16、Git 2.55.0、tmux 3.7c 来自共享的 bestfgs 环境。
- 100 题环境及依赖指纹核验报告保存在 `/mnt/lizh639/notebook-checks/second-*.json`。

本次结果：100/100 题环境指纹与源码导入通过；项目回归测试 288 项中 287 项通过、1 项跳过。核验报告为 `second-20260918T140627Z.json`，本机副本位于 `benchmark_results/notebook-setup/`。这些是基础设施检查，不是模型解题成绩或官方评测成绩。

系统依赖和 `/root/.bashrc` 位于容器层，Notebook 被删除重建后可能需要重新配置；共享目录内的代码、环境、清单和结果不属于这一层。

## 冻结清单

`/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen/task-plan.json`

计划校验值：`8e46676a0b79150c84a9fca745bed3638dd1f4f6e8bad6df4ca62405609affe7`。

包含原题 87 道、准备阶段替换题 13 道。两组必须使用这一份清单；正式实验开始后不因解题失败替换题目。本机副本为 `benchmark_splits/swe100_paired_dev_20260918.json`，换题审计为 `benchmark_splits/swe100_replacement_audit_20260918.json`。它是开发对照样本，不是原先保留的冻结测试集。

## 并行边界

此步骤只完成第二容器连接、依赖与环境核验，没有启动双容器实验，也没有修改求解算法或预算。

现有 `run_comparison.py` 对整个结果根目录加锁，不应直接在两台上重复运行同一命令。正式双容器执行前，须固定互不重叠的任务分片，让每台对所分任务都运行 Agent 和 raw 两组，并使用独立结果目录，最后验证合并恰好 100 个 ID。共享 Conda 环境和种子仓库在求解期间不得修改。
