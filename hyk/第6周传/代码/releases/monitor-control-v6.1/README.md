# BestFGS v6.1 工程修复（2026-10-01）

当前可用的 v6 修复版位于本目录。云端部署：`/var/tmp/lizh639-monitor-control-v6.1`。
它继承 v6 的决策机制和预算，只修复异常输入处理、依赖观测和异常定位。
冻结的 `monitor-control-v6`、v7 和已完成的 16 个 trial 均保留原样，云端哈希校验通过。

## 根因与改动

上次 v6 的五题工程故障实际为两类，之前把五题都称为同类错误不准确：

| 任务 | 根因 | 修复行为 |
|---|---|---|
| modflow6、foldseek、gdal、microscopy | 模型返回 `{"action":{"action":"run",...},"recovery_plan":...}`；字典被用于查询动作类型，抛出 `TypeError: unhashable type: 'dict'` | 先校验动作类型；返回明确的顶层格式纠正反馈，保留当前工作区。非法响应不执行。合法后续响应正常执行。 |
| great-expectations | 依赖路径推断把 Python 表达式当作文件名，6 个推断项中最长组件为 286 字符；Docker 内 `lstat` 抛出文件名过长错误 | 保守筛选可推断路径并检查路径长度；依赖探针遇到操作系统读取错误时将该项标为 `unknown`，继续观测其他项。 |

真实工程异常和交付异常现在还记录文件名、行号和函数调用位置；不将异常原文、源码行或局部变量写入新字段。
连续三个非法模型动作仍会按原预算触发 `model_or_protocol_error_limit`，不会伪装成工程故障。
路径推断只覆盖简单路径；明确注册的记忆目标仍支持空格等名称。`unknown` 不是文件缺失或验证成功。

## 验证结果

- 本地新增 6 项回归通过，包含上次四个真实嵌套响应的纠正后继续执行、连续非法响应的正确分类，以及路径探针错误处理。
- 云端完整离线回归 **342/342** 通过：HAI 123、Lean 38、提示视图 20、适配器 32、修复与语义测试 111、分类 7、监督器 11。
- 云端真实 Docker 验收 **10/10** 通过，零模型 API 调用，测试容器及镜像清理无错误。
- 四个嵌套响应分别在真实 Docker 中经历格式拒绝、脚本 Actor 纠正、真实修改、独立检查和文件交付。
- Great Expectations 的旧路径观测故障在 Docker 中复现；修复版执行原捕获的编辑命令并成功交付修改后的源文件。
- 修复版源码、原 v6 源码和封存实验双方源码哈希均校验通过。

证据：[离线回归](evidence/validation.json)、[Docker 验收](evidence/docker-validation.json)、
[上次失败输入](tests/v6_failure_responses.json)、[源码差异清单](changed-sources.json)。
云端 Docker 原始运行：`run-20261001-132244-72ea2e0a`。

本次是工程验收，未重新调用真实解题模型、未重跑官方八题评分。脚本纠正成功不保证真实模型总能纠正；修复后的算法收益需重新实验。
下一轮需要从 v6.1 新建干净 trial；不要重新启动或覆盖旧 16 题实验。

## 复现

在云端本发布目录使用已有实验 Python 环境：

```sh
python -B verify_release.py
INTEGRATION_CASES=monitor_control_v6_case,engineering_repair_case python -B cloud_suite.py
python -B check_integrity.py
```

`seal_release.py` 用于本地相邻 `monitor-control-v6` 目录的发布封存；运行后的源码清单已随部署上传。
