TACO task-local evolution on DSH — 0.1.0

入口：src/plugin.mjs。算法：worker.py + vendor/taco_native。
共享宿主、配置、验收与说明：../dsh-baselines/README.txt。
Python 依赖：pydantic==2.13.5；不需要原 Harbor 或独立 LLM 客户端。

范围经用户确认：每题从作者种子规则冷启动，保留规则选择/修改/生成、
动态过滤、第二层模型压缩、未覆盖大输出触发、投诉冻结/替换与信心更新。
全局规则池是原方法核心之一，本适配明确关闭题间读取和写回，不能称为
完整 TACO 全局演化复现，也没有使用冻结的训练期经验。

作者版本：2b048988e77ea67e6165450c97ebe66ce23a033f。
vendor 算法文件与历史 source-provenance.json 校验一致；唯一加载差异为
compression/__init__.py 不导入 POSIX fcntl 全局缓存模块，避免无用的
跨题缓存依赖。原 rule_cache.py 作为溯源材料保留，但运行时不加载。

TACO 改的是观测内容，原生工具执行、DTO、退出状态与权限由 DSH 保持。
DSH 工具的官方 finalizeContent 接口提交已过滤的可见文本，原文另存审计。
显式 taco_feedback 或作者投诉启发式触发恢复、冻结和替换。不能从一次
执行失败推断压缩丢失信息。规则生成失败沿用作者回退，并单独标记工程异常。

不添加解题子目标、搜索、回溯、Monitor/Advisor、大小模型路由或新技能系统。
