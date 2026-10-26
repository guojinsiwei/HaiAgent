HLD 视觉迁移准备版 0.0.1
日期：2026-10-23

状态
已建立独立源码副本和底座无关的视觉证据附件模块。
尚未选择或接通视觉 Agent，五角色未形成真实视觉执行闭环。
未部署服务器、未下载模型、未调用实验模型、未启动付费实验。

继承
frozen-hld-v8/ 来自 tb2-hld-mechanism-ab10-20261022/candidate。
RUN.txt 将该候选标识为 HLD v8；逐文件来源与哈希在 source-lock.json。
保留全部五角色源码及现有记忆机制；原项目不修改。
V9.1 属于独立效率实验，本次不混入效率改动。

已实现
src/visual-evidence.mjs 保存任务内截图、前后观察、公开动作回执。
视觉附件可关联已有 TaskMemory 的 M ID，供其检索后回看原始图像。
Planner、Solver、Monitor、Advisor、Critic 均可取得同源图像证据包。
不改变 TaskMemory 的准入、关键词检索、容量管理或经验使用逻辑。
工具成功与图像字节相同均不会自动认定任务成功、进展或语义循环。
视觉解释仍需实际视觉模型；当前测试不模拟宣称视觉理解能力。

尚待底座选定的工作
1. 将原 DSH scope/LLM/tool hooks 替换为视觉 Agent 的公开回调接口。
2. 配置真实视觉模型和多模态请求，把附件送入五角色。
3. 适配 visual observation / action / public receipt / stop。
4. 适配原 CLI 文件依赖、stdout 引文和交付物指纹。
   视觉模型判断不能伪装成机器已验证事实；需保留来源及不确定性。
5. 迁移角色提示和阶段验收，完整保留独立官方评分边界。
6. 接入全角色费用账本、取消、恢复及调用限额后做离线预检。

候选底座
A. AsgardBench 官方 VLM Agent 执行流程（AsgardBench 本身是 benchmark）。
   图像观察 + 高层物体操作，适合先验证任务内经验与语义重规划。
   https://github.com/microsoft/AsgardBench
B. OpenCUA 的 OpenCUAAgent + OSWorld 执行环境。
   截图 + 键鼠动作，适合桌面视觉任务；增加定位和虚拟机执行因素。
   https://github.com/xlang-ai/OpenCUA
底座、视觉模型、benchmark 三者分别记录，尚未做最终选择。

验证
运行 node --test tests/*.test.mjs，仅验证附件接口与原 TaskMemory 的衔接。
2026-10-23：4 项接口测试全部通过。包含五角色图像附件、原记忆不变、跨题隔离、
未知引用拒绝及工具成功不升级为任务成功。真实视觉闭环尚未验证。
frozen-hld-v8/tests 是继承测试，当前没有重跑其 DSH 集成依赖。
已知原 V8 回归存在历史失败，详见原项目 RUN.txt，不宣称整个 HLD 全通过。
