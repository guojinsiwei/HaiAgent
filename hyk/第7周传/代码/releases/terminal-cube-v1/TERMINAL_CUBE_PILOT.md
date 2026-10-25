# Cube-Studio TerminalBench 初测

这是从 interface-hardening-v5 复制出的独立版本，原 SWE 实验代码和结果不受影响。
学校文档：https://docs.qq.com/doc/DQ0VnWEN1RVVGRkNN
已核对：只开放 Notebook，不支持嵌套 Docker，可保存和复用 Notebook 镜像，最多同时运行两个 Notebook。
文档未提供自动逐题创建、重置容器的受支持接口。当前 Notebook 的 Kubernetes 服务账号也没有所需权限。

## 本轮范围

- `terminal_cube/dataset-lock.json` 固定 TerminalBench 2 的 89 个任务包哈希。
- 按项目原有划分排除 9 道冻结题，保留 80 道开发题；这是项目划分，不是官方训练/测试划分。
- 只初测 `polyglot-c-py` 和 `openssl-selfsigned-cert`，按依赖是否已具备选择，不代表随机样本。
- 每题分别运行 BestFGS 和 raw，共 4 次；两方法同模型、同预算：24 轮、80 工具调用、每动作最多 4 条命令、high reasoning、关闭自适应预算及独立 Judge。
- 一次运行每题最多 900 秒，顺序执行。没有自动重试或按失败结果换题。
- 只携带公开题面和环境定义，没有官方 solution、tests 或 verifier。

## 已知差异

把公开题面的 `/app/` 显式重定位为 `./`，以适配现有算法的文件快照；原题和校验值保存在 `terminal_cube/public_tasks`。
不安装原始 Docker 镜像，不自动翻译 Dockerfile。Notebook 的 Python/GCC/OpenSSL 版本与原镜像不同。
文件快照无法回滚系统服务、系统包、数据库和外部状态。这里也不是完整安全沙箱。
完整 80 题尚未适配，不能把这两题的入口直接扩展到所有题。

所有报告固定 `official_evaluation=false` 和 `official_reward=null`。
`agent_succeeded` 为内部判断；`public_smoke_passed` 是根据公开题面编写的不完整检查，不能作为官方成功率。
轮次、调用数、重复调用率沿用 SWE 的同一记账逻辑；重复率指同命令、同文件状态、同观测且无文件变化的重复调用，不等于语义冗余。

## 在学校 Notebook 终端运行

```bash
cd /mnt/lizh639/BestFGS-terminal-cube-v1
# 无需把密钥写入命令，脚本会隐藏输入；若终端已有环境变量则直接使用。
bash start_terminal_cube_pilot.sh
```

脚本显示结果目录，保留该终端直到完成。运行后可在另一个 SSH 终端查看：

```bash
cd /mnt/lizh639/BestFGS-terminal-cube-v1
/mnt/lizh639/envs/bestfgs/bin/python run_terminal_bench_cube.py report --output-root <上一步的结果目录>
```

只做预检，不调用模型：

```bash
/mnt/lizh639/envs/bestfgs/bin/python run_terminal_bench_cube.py preflight
```

每次必须使用新的结果目录，避免把不同尝试合并。结果包括任务版本、原始环境定义、实际环境版本、共同预算、每方法每题日志、候选快照、交互轮次及工具重复率。

## 完整评测尚需解决

正式 80 题需要逐题的原始环境以及可靠的初始化/恢复机制，之后接入 Harbor 官方 verifier。
按当前文档，需平台管理员提供受支持的任务环境方案或另用能管理原始容器的运行节点。
自行保存一个通用 Notebook 镜像不等于已经复现 80 个题目环境。
