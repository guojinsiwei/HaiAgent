# Cube-Studio Notebook 运行后端

新入口 `run_notebook.py` 直接在已创建的 Notebook Ubuntu 容器中启动 Python，
不调用 Docker、WSL 或 Cube-Studio 管理 API。Notebook 的创建、CPU/内存申请和 SSH
仍在学校平台完成。只调用远程模型 API 时，通常不需要 GPU。

## 部署

把完整项目上传到 `/mnt/<NETID>/BestFGS`，在 Notebook 的终端操作：

```bash
cd /mnt/<NETID>/BestFGS
python3 --version  # 必须 >=3.11；否则先选择/安装符合要求的 Python
python3 -m venv /mnt/<NETID>/bestfgs-venv
source /mnt/<NETID>/bestfgs-venv/bin/activate
python -m pip install -e .
# 在当前终端安全配置所选服务商的 API Key 环境变量；不要写进任务 JSON。
# 例如 DEEPSEEK_API_KEY；也支持 OPENAI_API_KEY、DASHSCOPE_API_KEY。
```

任务代码、虚拟环境、项目和结果均应放在文档承诺持久化的 `/mnt/<NETID>` 下。
不要把结果保存在容器 `/tmp`。Notebook 重置后需重新激活环境并配置密钥。
运行器不会打印或保存密钥值；但智能体命令继承进程环境，因此不能当成安全沙箱。
不要把学校凭证或无关敏感文件放进该 Notebook。

## 准备任务

参考 `examples/notebook_tasks.template.json`，创建自己的 `tasks.json`：

- `benchmark`：`custom`、`swebench` 或 `terminal-bench`。
- 每题需要唯一 `id`、公开 `goal`、已经准备好的 `workspace` 目录。
- `success_criteria`、`constraints` 是可选字符串列表。
- 相对工作区路径以 JSON 所在目录为基准。种子和输出目录不得互相包含。
- SWE-bench 还需要完整 `base_commit`；工作区必须是该提交的干净 Git checkout。
- 冻结测试集题目在这个开发入口仍被禁止；不要通过改 benchmark/id 绕过保护。

**任务准备不是只下载代码。** 原镜像安装的语言、依赖、数据库、工具和数据必须
先准备在 Notebook。运行器不会自动翻译 Dockerfile，也不会执行 JSON 中的安装脚本。
种子目录必须不含符号链接，包括 Git worktree 等通过外部目录共享状态的布局。
不要把虚拟环境放进种子：快照会复制种子文件，造成严重空间浪费。

## 启动

```bash
python run_notebook.py --task-manifest tasks.json \
  --output-root /mnt/<NETID>/bestfgs-runs/dev-01 --dry-run \
  -- --provider deepseek --model YOUR_MODEL

python run_notebook.py --task-manifest tasks.json \
  --output-root /mnt/<NETID>/bestfgs-runs/dev-01 \
  -- --provider deepseek --model YOUR_MODEL
```

`--` 后沿用 `python -m bestfgs` 的求解模型、预算和搜索参数。
独立 LLM 结果审计已撤下，所有主入口仅允许 `success-judge-mode=off`，无需 Judge Key。
旧 `SUCCESS_JUDGE_*` 环境变量不参与 Notebook 运行配置或恢复指纹。
任务目标、工作区、运行目录和任务约束只能在清单配置，不能在透传参数覆盖。
`--python /absolute/path/to/venv/bin/python` 选择任务依赖所在解释器，
该解释器目录也会加入命令 PATH。每批使用同一套依赖，不适合混合互相冲突的环境。
`--task-timeout` 默认每题 14400 秒，超时终止该题进程组并记录 error。
任务按顺序运行，避免同一个 Notebook 的共享服务和资源相互干扰。

原主启动文件也支持新后端，`--backend` 必须放在开头：

```bash
python run_swebench.py --backend notebook --task-manifest swe-tasks.json \
  --output-root /mnt/<NETID>/bestfgs-runs/swe-dev -- --provider deepseek
python run_terminal_bench.py --backend notebook --task-manifest terminal-tasks.json \
  --output-root /mnt/<NETID>/bestfgs-runs/terminal-dev -- --provider deepseek
```

该模式采用清单选择任务，**不使用旧 Docker 入口的自动抽题/Harbor 参数**。
历史固定子集和 frozen 启动脚本仍属于旧 Docker 流程，没有伪装成可用的 Notebook 版本。
旧后端暂时保留，便于官方评测和复现实验；省略 backend 仍是历史行为。

## 持续运行和恢复

长实验建议用 Notebook 的 SSH 终端及 `tmux`（如有），在会话中执行上述命令。
浏览器断开不等于容器停止，但 `tmux` 无法防止平台回收、OOM、重置或宿主机故障。
平台是否限制持续运行时间，需要向管理员确认，不能承诺永久不中断。

每题有 `status.json`；每次尝试独立保存 `agent.log`、`agent-result.json`、
`snapshots/` 和算法 checkpoint。批次有 `notebook-run.json`、`summary.json`。
SWE-bench 额外保存每题 `model.patch` 和批次 `predictions.jsonl`，可交给独立
官方 harness 评测；补丁导出使用临时 Git index，不修改候选原 index。
查看日志可用 `tail -f <attempt目录>/agent.log`。

重新执行相同命令，增加 `--resume`：已完成题目跳过，错误/中断题建立新尝试重跑。
**不是搜索中途恢复**：现有算法没有 checkpoint 加载能力。
内部未成功但正常结束的题也算 completed，不会自动反复烧 API。
改变代码、种子、解释器路径、参数或已记录模型环境配置后必须使用新输出目录。
运行锁阻止两个运行器同时占用同一目录；依赖包、系统服务和模型服务端变化不在
指纹保护范围内，正式实验仍需另存环境版本。退出码 0 表示批次正常完成，
不代表所有题成功；2 表示基础设施/任务执行错误；130 表示用户中断。

## 隔离和评测边界

核心搜索、记忆、压力控制、前沿选择均未修改。每个动作仍从父状态复制文件快照，
最终 `best_workspace` 是保存的候选目录，不会覆盖原种子。

文件快照**不是容器快照**：不能回滚系统包、绝对路径文件、数据库、端口、环境变量
或外部服务。需要这些状态的题应单独创建并准备 Notebook，在干净状态下运行，
不能直接认定与官方镜像等价。Notebook 中的任意 Python 代码没有 OS 级隔离，
命令白/黑名单也不能解决这个问题。不适合执行不可信代码或与其他实验共用敏感环境。

所有新后端结果固定记录 `official_evaluation=false`，`agent_succeeded` 是内部诊断，
**不能当作 SWE-bench resolved / Terminal-Bench 官方 reward**。
学校文档禁止容器内嵌套 Docker，官方 SWE-bench harness 和当前 Harbor Docker 环境
不能原样在这里运行。正式指标应导出候选后，在支持官方环境的独立评测机器验证，
或另行完成并核验非 Docker 评测适配。隐藏测试不能交给模型查看；本入口不执行隐藏
verifier，也不把其位置写进任务清单。迁移运行基础设施不意味着评测环境已等价迁移。
