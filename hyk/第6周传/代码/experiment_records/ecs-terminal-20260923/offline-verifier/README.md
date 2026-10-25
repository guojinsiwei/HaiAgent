# TerminalBench 验证依赖离线缓存

本目录用于解决阿里云 TerminalBench extended-v2 在 uv、CPython 与 Python 测试包下载时卡住的问题。

**2026-09-24 已完成：依赖上传、云端 SHA 校验、36/36 断网依赖预检；原实验已恢复到 `01-compile-compcert-bestfgs`。** 此为恢复时的状态快照，最新进度请运行文末查询命令。云端证据副本见 `cloud-recovery-proof.json`。

## 范围

- 36 个题目，BestFGS / Raw 两组，共 72 条试验记录。
- CPython 3.13.9、uv 0.9.5、pytest 8.4.1、pytest-json-ctrf 0.3.5。
- 52 个题目专用依赖归档，共 3,441,956,536 字节，逐个核对官方 SHA256。
- `pytorch-model-cli` 遵循题目明确配置的 CPU 索引，使用 torch 2.7.1+cpu / torchvision 0.22.1+cpu。
- `torch-tensor-parallelism` 保持 PyPI 的 torch 2.7.0 及其 CUDA 依赖。
- 只有验证阶段能接触缓存；模型、算法、预算、官方题目内容、测试与奖励规则保持原样。
- 系统软件的 apt 安装、题目自身需要的网络访问仍保持原逻辑。这不是全任务断网运行方案。

## 验证与恢复

`preflight_cache.py` 在每道题固定的原始 Docker 镜像中关闭网络，安装其测试依赖并运行一个合成 pytest 测试，确认 CTRF 报告成功产生。此检查不调用模型，也不产生 benchmark 分数。

全部 36 项依赖检查通过后，`deploy_recovery.py` 会备份旧协议并建立基础设施修订记录，然后恢复原实验。新调度进程跳过已有唯一最终结果，避免自动重跑已付费的试验。

缓存清单、前后协议哈希、每题依赖预检记录均保存在云端：

`/home/ecs-user/terminalbench-offline-recovery-20260924`

原实验结果目录：

`/home/ecs-user/terminalbench-paired36-20260923-extended-v2`

## 前三条历史记录

详见 `historical-infra-audit.json`，原始结果和日志均保留，未被重写。

| 试验 | 原始记录 | 审计结论 |
| --- | --- | --- |
| gcode-to-text / BestFGS | VerifierTimeoutError | uv 下载超时，测试未启动 |
| gcode-to-text / Raw | reward=0 | uv 下载失败，uvx 不存在，测试未启动 |
| compile-compcert / Raw | reward=0 | Python 下载超时，测试未启动 |

三条均为基础设施导致的无效评测，不能作为模型答错的证据。统计保留原 reward，并把模型成功状态设为未知。它们没有自动重跑；原容器已清理，不能假定仅凭已有轨迹能够无损重建完整系统状态。

最终比较应明确有效样本数，并以两组都完成有效评测的共同题目计算配对指标；不能把两组不同的有效分母直接混作配对提升。

## 本机查看进度

在 PowerShell 运行现有状态查询脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\ChatGPT\mcts\experiment_records\ecs-terminal-20260923\Check-Terminal36-extended-v2.ps1"
```

SSH 查询失败只表示这次连接失败，不能据此判定任务已停止，也不要因此重复启动实验。
