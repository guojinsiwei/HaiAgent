# 学院 cubestdio Notebook 迁移

当前状态：已准备 Linux 主机兼容和只读环境检查；每道题的 Docker 后端尚未替换，官方评测尚不能宣称已在学院 Notebook 上运行。

## 在学院 Notebook 中检查

把 BestFGS 上传到学院提供的持久化目录，在 Notebook 的 Terminal 中进入项目目录，运行：

```bash
python3 notebook_preflight.py --workspace /实际的任务仓库目录
```

需要 Python 3.11+ 和 bash；任务还需要自己的依赖。检查只显示密钥是否存在，不显示密钥内容，不下载镜像，不访问模型服务。`official_benchmarks_ready` 在学院任务后端接入完成前固定为 false。

Agent 核心可以直接运行，不需要在 Notebook 内再启动 Docker。完成任务依赖安装后，可以使用下面的入口；它会实际消耗模型 API，密钥应由学院平台环境变量注入：

```bash
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m cli_retrac_mcts \
  --provider deepseek \
  --workspace /实际的任务仓库目录 \
  --run-root /实际的持久化目录/bestfgs-runs/唯一任务名 \
  --goal '实际任务的公开问题描述' \
  > /实际的持久化目录/bestfgs-runs/任务结果.json
```

先创建输出目录，使用专门的任务 Notebook，按学院要求配置持久化存储。Agent 的分支复制只隔离工作区文件，不隔离系统软件包、进程或挂载目录，不能代替每题容器隔离。该命令的内部验证结果也不能代替 SWE-bench/Terminal-Bench 的官方通过率。

## 已完成的主机适配

- Windows 主机继续通过 WSL 执行 Linux 命令；Linux Notebook 直接执行这些命令。
- 任务发现、日志读取、结果读写、job 目录检查不再在 Linux 上调用 `wsl.exe`。
- Linux 使用原生路径并直接继承密钥环境变量。
- 现有 Docker 模式仍使用 Docker；Linux 默认可执行文件改为 `docker`。

这一步只解决运行评测编排程序的主机兼容问题，尚未把 Docker 容器变成平台 Notebook。

## 学院平台还需提供的信息

1. 平台访问地址，以及 Notebook 的 SSH 地址/端口/用户名或可用的命令执行接口；不用提供密码或私钥。
2. 能否选择自定义任务镜像、是否支持批量创建/停止 Notebook，相关 API 或管理员给出的操作说明。
3. Notebook 的持久化目录、可用 CPU/内存和同时运行实例数。

SWE-bench 每题原来使用官方实例镜像中的 `/testbed` 和任务依赖；迁移后需要按相同环境建立独立 Notebook，执行 Agent、收集 patch，并在干净环境进行官方测试。当前 `swebench.harness.run_evaluation` 入口仍是 Docker 评测流程，不能直接当成 Notebook 后端。

Terminal-Bench 原来通过 Harbor 的环境接口上传代码、执行命令并运行 verifier；需要适配学院 Notebook 的生命周期、文件传输、命令执行和结果下载，以及任务镜像中原有的工作目录、依赖和服务。

在连接方式未明确前，不假设学院开放 Kubernetes 权限、创建 API、自定义镜像或 Docker daemon。接入后先做不调用模型的环境和测试流程验证，再运行小样本正式评测。
