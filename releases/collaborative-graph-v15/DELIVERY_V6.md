# v6：停止与补丁交付修复

日期：2026-09-21。修改基线：`../interface-hardening-v5` 的副本。
原 v5、SWE100 题单、云端代码、结果与历史评测均未更改。本次不调用付费模型、不启动云端运行、不重新评测 100 题。

## 为什么过去的修补没有覆盖问题

v5 末次复验失败时保留补丁的逻辑，只保护已经登记的已验证候选。候选登记入口仍要求 `intent=candidate`，且首次功能验证失败不登记；探索阶段的实际源码修改也可能漏掉。没有入库的修改无法被末端 fallback 挽救。

此外，`candidate + 工作区指纹变化 + 自选测试通过 + 模型声明标准覆盖` 可以自动生成 `verified_success`，即使模型的 `task_success=false`。指纹还包含 `.git/index` 等元数据，和最终 Git 补丁是否非空不是同一个判断。仅重复执行原来的局部测试不能证明验证范围完整。

## 参考实现与取舍

- [mini-swe-agent 显式提交协议](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/environments/docker.py#L140)：把提交作为控制信号，不把模型自评当官方成绩。本实现使用严格布尔字段而不是容易与普通输出混淆的 stdout 标记。
- [mini-swe-agent 提交配置](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/config/benchmarks/swebench.yaml#L75)：区分制作、检查和提交补丁。本实现要求在已有补丁上用单独只读动作明确提交。它比上游协议更严格，是本项目的设计选择，不是上游保证正确性的机制。
- [SWE-agent 异常自动提取补丁](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/agent/agents.py#L823)：停止原因与已有制品分别保存。本实现固定初始 base，使用外置临时 Git 索引/对象目录，不修改候选自己的 Git 索引。mini-swe-agent 的预算耗尽路径可能返回空提交，不能把它作为自动抢救补丁的依据。

没有引入新的 LLM 裁判、参考补丁、隐藏测试或跨任务记忆。

## 新的契约

1. **候选存在与正确性分离。** 实际可导出的改动进入候选管理；首次测试失败、没有验证、explore 标签不再导致草稿消失。已有公开验证通过的候选优先，否则保留最新草稿。候选排序不再把测试命令数量或语义覆盖率当作补丁正确性分数。
2. **真正检查制品。** Git 任务按初始 HEAD（准备后的固定提交）计算真实 patch；排除 `.git`、`__pycache__`、`.bestfgs_runs`。支持新增、删除、暂存和未暂存文件。不能靠文件名猜测所有新文件都是临时脚本，因此非空 patch 仅表示制品存在，不表示修复了源码逻辑。
3. **显式结束。** `MacroAction.submit` 默认为 false；`candidate` 只表示候选操作。模型必须在已有非空补丁上发出 `intent=candidate, submit=true` 的只读复核动作。执行前后补丁哈希必须一致，声明的普通命令与公开验证必须完整执行且通过。覆盖率、`task_success`、成功标准列表本身不能结束任务。已 covered 的方向仍允许此提交动作，但正常预算、去重和工具安全限制仍生效。
4. **绑定本次证据。** 完整提交动作已对同一补丁执行验证，交付前再次检查哈希后复用这些结果，不强制再跑一遍相同测试。其他候选的末次复验仍在预算内；未执行、失败、异常分别记录。验证执行后抛异常时保守占用声明的验证额度，避免异常带来额外免费调用；实际研究指标仍来自统一 recorder。
5. **正常结束和异常都保留草稿。** 执行后、模型评估前写检查点；运行时异常、进程坏退出或超时从当前 attempt 内的有效检查点抢救，并核对路径、固定基线和补丁哈希。异常仍记作异常，不伪装完成或自动重跑。检查点若损坏/越界/与实际补丁不一致，明确拒绝。
6. **状态不再混用。** `submitted` 表示显式交付被接受；`delivery.has_patch` 表示有制品；`local_validation_passed` 只表示当前补丁的公开检查通过；`official_resolved` 在求解阶段始终为 null。默认模式不生成 `succeeded=true` 或 `verified_success=true`。正常非空草稿也可退出 0（程序正常结束），不等于题目通过。异常保留非零退出与错误原因。

库配置保留 `termination_mode=legacy_verified`，只用于清楚标记的历史回放/消融测试；生产 CLI 默认 `explicit_submission`，不提供切回旧自动成功模式的开关。新交付回归全部使用新默认。

## 固定历史诊断案例

来源：本项目 `official-eval/swe100-v3-bestfgs/bestfgs-batch-543f784a24bbdce3/results.json`，SHA256 `241e3e3e1f20f1fb3c92887bd03f4f822c9018b3c2f39547c258fe28d9e53bfe`。
基线来源：`official-eval/swe100-v3-raw/bestfgs-batch-a3c9cc7b0b496ff3/results.json`，SHA256 `60a8bc977ee5cd4889fadbe4e97bd8326b3cc8a49bc21bb1049dea44a2f4bd1e`。

- `django__django-15252`、`django__django-13023`、`django__django-15957`：BestFGS 内部 verified_success，官方 unresolved，而 raw 通过。用于固定“自报通过不等于官方通过”的诊断对象；不能仅凭这些汇总记录断定各题同一根因。
- `django__django-14053`、`sphinx-doc__sphinx-8551`：BestFGS 预算耗尽、空补丁，而 raw 通过。用于固定候选保留与导出检查对象。
- `django__django-10554`：BestFGS 内部 verified_success，最终却为 empty_patch。用于固定真实 Git 差异门槛检查对象。

本次回归以小型真实 Git 仓库复现同类链路错误，并不是重新执行上述 SWE 任务，也不证明这些题在 v6 已经解决。未读取参考修复或隐藏测试来设计求解行为。

## 离线验证

2026-09-21 在 Windows / Python 3.12.14 完成全量验证：**350 项，344 通过、6 项平台条件跳过、0 失败**，耗时 61.840 秒。包含 12 个真实 Git 交付链路反例。跳过项为 5 个 POSIX/Linux 专属旧测试和 1 个当前权限不允许创建符号链接的补丁测试；不能据此声称 Linux 路径已经全部实测。机器可读记录见 [VALIDATION_V6.json](VALIDATION_V6.json)。

在本目录、Python 3.11+ 与 Git 可用的环境中：

```bash
PYTHONPATH=src python -m unittest discover -s tests -q
```

Windows PowerShell：

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -q
```

重点文件：`tests/test_delivery_runtime.py`（真实 Git 生命周期）、`tests/test_submission.py`（补丁与固定 base）、`tests/test_notebook_runner.py`（退出、超时、检查点、哈希）、`tests/test_environment.py`（验证副本隔离）、`tests/test_retrac_adapter.py`（提交协议）。

Windows 上的验证副本清理也已修复：只处理已验证在 run_root 下的临时 verification 子目录里的只读 Git 对象，不改变种子仓库或候选快照的权限。链接权限、进程组等平台限制的跳过项必须如实记录。

## 不应声称什么，以及下一步

- 这次解决的是可重现的停止/交付契约问题，**没有证据表明成功率已超过 62% 或 79%**。
- 显式提交与非空补丁不能保证测试覆盖完整；公开测试仍可能不足。`local_validation_passed` 不是 correctness oracle。
- 不能保证所有崩溃零损失：若执行进程在首个有效检查点之前被强杀，或检查点/工作区损坏，仍可能无法抢救。
- 原始调用、工具和动作预算未增加，但独立只读提交会消耗预算内的步骤；跳过重复最终验证是行为变更，不是修改冗余率定义。搜索评分、记忆提取、模型/API、冻结题单未在本次重新调参。
- 后续须先做少量开发题冒烟运行，再决定是否扩大实验；不自动上传或启动。旧 100 题已参与诊断，只能作为开发数据。新版本应使用新的运行目录和实现/协议哈希；不能沿用 v5 的冻结哈希或将新版轨迹混入旧结果。
