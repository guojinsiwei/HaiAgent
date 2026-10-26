本地候选：正交探索触发修复，2026-10-17。
基线：../kz-native-tb2-tls3-20261017/native。
当前未部署、未运行付费实验。
修改集中于 native/legacy/sources/bestfgs-project/src/bestfgs/ 下的
exploration_trigger.py、contrastive_exploration.py、lean_runtime.py。
新增测试：native/test_exploration_trigger.py。
完整修改与验证说明：../../experiment_records/tb2-orthogonal-trigger-audit-20261017/CHANGE-REPORT.txt。

追加：已实施相关记忆检索、单维正交突破、预测结果回写与探测步数分离。
仍为本地未部署候选；新协议要求 changed_dimensions 和 exploration 观测预测。
最新说明：../../experiment_records/orthogonal-learning-20261017/REPORT.txt。
