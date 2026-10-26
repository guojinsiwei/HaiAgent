# 修复验证记录

状态：**修复版已上传部署；本地与云端各 190 项回归通过，Ubuntu 与 MATPOWER 云端集成验收均为 13/13 PASS。**

原冻结 HAI / BestFGS 代码、原云端实验部署和旧实验结果均未修改。本次代码修改只位于
本地 `releases/mechanism-integration-fix-v1` 及其云端独立修复副本。

## 已通过的本地检查

使用本地 WSL Ubuntu Python，关闭字节码写入，不调用模型 API：

| 测试集 | 数量 | 结果 |
|---|---:|---|
| HAI 原有完整测试 | 123 | PASS |
| BestFGS lean 运行时及 Docker 适配器原有测试 | 38 | PASS |
| 原有提示视图测试 | 20 | PASS |
| 新增修复专项测试 | 9 | PASS |
| 总计 | 190 | PASS |

新增检查包括：`/app` 与宿主别名及子目录区分、紧凑记忆保留证据和适用条件、
旧记忆仍标记 historical、提示预算不变、shell 诊断触发、拒绝不明确或写入形式、
保留未知证据拒绝、区分数量错误、预算分类不掩盖已知服务错误。

回归命令（从修复版根目录，在 WSL / Linux 中执行）：

```sh
PYTHONPATH=sources/hai-project/src python3 -B -m unittest discover -s sources/hai-project/tests -q
PYTHONPATH=sources/bestfgs-project/src python3 -B -m unittest discover -s sources/bestfgs-project/tests -p 'test_lean*.py' -q
PYTHONPATH=sources/bestfgs-project/src:sources/bestfgs-project python3 -B -m unittest discover -s sources/bestfgs-project/tests -p test_prompt_views.py -q
python3 -B -m unittest discover -s tests -v
```

## 云端验收

已准备 13 项云端验收：原 12 项，加 HAI memory intervention → changed action →
observed follow-up 的实际 Docker 行为链。四证据用例改为验证“上限已明确声明且
准确拒绝”，没有取消三条证据上限；这不是让非法输入通过。

压缩包：工作区 `tmp/mechanism-integration-fix-v1.tar.gz`。
服务器：`lizh639@172.16.108.236`。
上传路径：`/var/tmp/lizh639-mechanism-integration-20260929/repair-v1.tar.gz`。
解包路径：该测试目录的 `repairs/mechanism-integration-fix-v1`。
实际上传包 SHA-256：`c5c641434888d6b3f3aee5d04211316b101ae934abf87aadf3c7a9a0bd069770`。

自动安全审查曾阻止这份新 payload 的上传。用户随后明确批准上传并直接测试，
正常上传成功；没有通过其他传输方式绕过审查，也没有在云端原实验目录原地修改代码。

上传后已验证包哈希、修复版源清单及冻结原实验源哈希；云端现有 Harbor 运行时下
190 项回归全部通过，日志位于工作区 `experiment_records/cloud-integration-repair-20260929`。
Ubuntu 完整集成验收为 13 PASS / 0 FAIL / 0 ERROR，运行 ID 为
`run-20260929-211328-745199e6`，232.016 秒，正常清理。
MATPOWER 同镜像复测也是 13 PASS / 0 FAIL / 0 ERROR，运行 ID 为
`run-20260929-211815-16bb0729`，271.052 秒，正常清理。两轮清理错误均为零，
所有权日志中无剩余测试容器和快照镜像。

完整报告位于工作区 `experiment_records/cloud-integration-repair-20260929/REPORT.md`。
本次不运行付费模型或正式评分器；不得声称正式任务分数已提高。
