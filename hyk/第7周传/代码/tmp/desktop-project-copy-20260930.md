# 项目副本说明（2026-09-30）

本副本的 src、tests 和 examples 来自本轮六题配对试跑：
experiment_records/lhtb-paired6-repair-v2-20260929。
方法源码为 mechanism-conversation-fix-v2 修复版，并按该试跑的
release-source-verification.json 校验。原项目与云端运行不受此次复制影响。

pyproject.toml 和 README.md 从对应的原项目补入，便于安装和了解接口；
原有包版本号保持不变，不代表此次修复的独立版本号。
最新修复说明见 REPAIR-README.md 和 REPAIR-VALIDATION.md，优先于旧 README。
release-source-verification.json 同时列出两项目的源码，核验本包时按项目名前缀筛选。

这是项目源码副本，不是完整云端实验环境镜像。未附 Docker 镜像、基准数据、
正式实验评分器、主机专用调度脚本或运行结果。未附密钥、Python 缓存、IDE 配置、
生成的 egg-info。未修改算法代码；未额外调用模型或重跑实验。

Python 要求及入口见 pyproject.toml；在合适的独立 Python 环境中可用
`python -m pip install -e .` 安装。特定 Docker/基准实验仍需其对应外部运行环境。
