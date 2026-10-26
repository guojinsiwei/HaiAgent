SUZ 0.2.0 — 基于 OpenCUA 的桌面视觉长程任务控制器
2026-10-23

这版做了什么
SUZ 是独立项目，面向看屏幕、点击、输入、滚动的软件操作任务。
沿用 HLD v8 的 TaskMemory 与 SemanticPlanner 原始代码；视觉角色提示、证据接口、
完成审查和执行衔接在本项目新建。五角色已接入完整调用链。
旧 HLD 项目、已有实验、服务器和 API 密钥均未改动。

0.2 新增：局内失败经验的视觉标注
Advisor 诊断反复无效的点击，并给出当前截图上的目标框、适用条件、原因和置信度。
标记至少引用 2 次实际执行观察，目标框必须覆盖其中一个实际点击位置；
证据纳入原 TaskMemory，V ID 对应 M ID、E ID 和 F ID。不能给未尝试的区域凭空画叉。
较明确的禁用、遮挡、手势问题画半透明红叉；加载中或原因未知画黄色提示框。
Solver 收到未改动的原图，以及同尺寸、同坐标的标记副本；原生 OpenCUA 历史仍用原图。
Monitor、Critic 只看未标注图像，人工红叉不进入界面状态证据。
标记关联任务内语义对象及界面条件；图像变化后需要 Monitor 定位、复核再激活，
到第 3 个后续观察步强制过期，复核不会延长期限；条件消失可提前撤销。
红叉提示历史失败，允许有新依据的重试；没有新增硬性禁点规则。
Advisor 还接收最近一次点击附近的前后原始截图放大裁剪，每图带原始归一化坐标。
像素测量增加 RGB 缩略图平均绝对差和显著变化比例；没有把它冒充 SSIM 或语义进度。
发现 A-B-A-B-A 页面往返或连续低变化时，立即请 Monitor 审查；像素线索单独不判失败。
Planner 的首次观察明确检查软件/窗口、遮挡、焦点、加载与登录状态，按需提出低风险观察。
候选路线覆盖菜单、快捷键、应用内搜索和焦点导航，按目标等价性选择，避免强制换操作模态。
后台命令仍禁用；跨软件路径须保持输出格式、目的地、账户权限和保存要求。
此前 0.1.0 的自有源码已存入 versions/v0.1.0-source.zip；vendor 与 frozen-hld-v8 始终不变。

红叉的独立对照开关
visual_warnings=true：保留条件化区域经验及文字指导。
visual_overlay=false：只关传给 Solver 的标记图，保留同样的记忆/诊断/路线，用于测红叉增益。
diagnostic_crops=false：关闭 Advisor 放大图。
visual_metrics=false：关闭近似差分及解码像素测量；现有精确图像比较仍保留。
修改配置后仅影响新建运行。默认开启以上功能，真实模型调用仍关闭。

当前状态
可运行的本地研究实现，已完成脚本化离线端到端验证。
官方 OpenCUA.predict、历史截图构建、输出解析及坐标投影都实际参与离线测试。
真实视觉模型、OSWorld 虚拟机端到端尚未运行，不能据此声称具备识图能力、
能够破解真实操作循环或已经提升成功率。没有下载模型权重、没有付费调用。

五角色
Planner：围绕完整目标维护多步操作路线；评估候选，遇停滞更换语义方向。
Solver：使用固定版本官方 OpenCUAAgent，读取截图、生成 PyAutoGUI 动作。
Monitor：比较动作前后的原图与目标进度；记录条件化经验，发现停滞或退步。
Advisor：停滞时提出局部原因和可区分原因的低成本观察，供 Planner 参考。
Critic：把公开任务拆成固定验收义务，保留完整目标 G0；完成时逐项审查当前可见证据。
本项目采用语义路线重规划，没有增加正交约束，也没有删减角色。

记忆继承与视觉适配
frozen-hld-v8/src/memory.mjs 原样复用，保留准入、关键词检索、容量与经验复用检查。
src/visual-evidence.mjs 关联原始截图、前后观察、动作和公开回执。
经验仍限于单题。每条经验保持原有 M ID，并引用 E ID 的动作前后原图。
GUI 状态采用 unknown:visual，避免把图像哈希伪装成 CLI 工作区依赖指纹；
检索结果须重新核对页面、对话框和操作对象条件。视觉解释标为模型判断。
检索文字最多 4 条，原图回看最多关联其中 2 条；角色还看到最近 3 次动作。
Planner 必须对可见记忆声明采用、复核、换路线、不适用或有新证据的重试；
路线关联继续进入实际动作记录，便于审计经验是否影响后续选择。
该关联本身不能证明因果收益，日志保留 causal_benefit_proven:false。

触发与完成
默认每 2 次观察运行 Monitor，每 8 个路线动作进行周期评估。
同一路线连续 3 次相同动作且每次前后图像完全相同，会产生循环候选并要求重规划。
Monitor 有当前路线至少 2 次执行证据时，可以触发停滞重规划；画面改变不自动算进展。
初次规划与停滞生成 1–2 个新方向；周期评估可以继续有效路线。
拒绝重复无效路线、未知证据和空洞路线对照，候选窗口保留 6 条。
初次 Critic 建立义务；Solver 提议 DONE 后，Critic 必须逐项引用当前截图。
旧图、工具成功、全局 accept 均不能统一关单。保存/持久化看不出来时需要继续检查。
Critic 通过标为 visually_accepted，官方成绩始终由环境在解题结束后独立计算。
连续 3 次未经支持的完成声明停止并保留未完成状态，避免无限交卷审查。

OpenCUA 的来源和改动边界
官方仓库：https://github.com/xlang-ai/OSWorld
固定 commit：04718eab9327856efe8192cc58161acc7a7627e2
目录：mm_agents/opencua，完整来源和 SHA256 见 upstream-lock.json。
vendor 文件原样保留，附带官方 Apache-2.0 LICENSE；运行时仅重定向私有模块导入路径。
本项目子类覆盖传输和外层控制，保留官方的模型提示主体、3 图历史、L2 格式、
响应解析、qwen25 坐标投影。任务截图尺寸从实际 PNG 读取。
原官方传输的硬编码地址、关闭 TLS 和大量网络重试没有进入 SUZ 调用链。
原 reset 中未导入 logging 的问题，通过始终传入 logger 避开，vendor 不修改。
GUI 动作加 AST 白名单，只允许静态键鼠、有限等待和剪贴板写入，不执行任意 Python。
该白名单约束代码语法，无法保证模型不会通过键盘输入尝试走终端路线；
两组共享的 GUI-only 提示明确禁用终端/开发者控制台/API/DOM，实跑需审计违规动作。

比较模式
config.mode=suz：五角色＋任务内记忆＋官方 Solver。
config.mode=opencua_baseline：同一 Solver、传输、费用限额、GUI 边界和环境，关闭 SUZ 角色与指导。
后续可固定 solver_model、题目、环境、采样、步数和总费用，进行接入前后比较。
这份 baseline 是“统一执行边界的固定 OpenCUA”，需披露共享 GUI 限制与传输改动；
不能把得到的分数直接标成论文原始实验复现。

费用、停止和记录
所有 Solver/Planner/Monitor/Advisor/Critic 共用 cost-ledger.jsonl 和请求上限。
调用前按配置单价和输入输出硬上界预留；收到完整 usage 后结算，缓存优惠不自行猜测。
未收到 usage、传输中断会保留预留额，停止本题，避免漏算后继续消费。
本版 live 传输要求 /v1/models 提供 max_model_len，且不超过 max_input_tokens；
用服务端完整上下文长度作为输入保守上界，另外预留最大输出费用。
限额/传输异常可穿透官方内部重试循环；解析格式失败的官方重试仍逐次记账。
目前为单题运行入口；没有付费批量调度器或跨进程共享整轮预算。
默认 allow_live=false、预算为 0。密钥只从配置指定的环境变量读取。
记录 controller.json、mechanisms.jsonl、agent.jsonl、原始 frames/*.png、完整费用账本。
它们可能包含任务截图和任务内容，应保存在实验工作区内。
保存了状态与证据，支持离线回放审计；没有自动恢复真实桌面任务功能。
运行目录禁止覆盖，避免误重跑或错误继承题目记忆。

本地运行
需要 Node >=22 和 Python >=3.11。
在本目录：
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  node scripts/preflight.mjs
  node --test tests/*.test.mjs
  .venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
  node scripts/offline-demo.mjs
Linux 将 .venv\Scripts\python.exe 替换为 .venv/bin/python。
离线 demo 用人工构造截图和脚本响应，不发网络请求、不控制桌面；结果保存在 runs/offline-*。

接入真实实验前
1. 在独立实验环境准备官方 OSWorld（建议同一个固定 commit）和独占测试虚拟机。
2. 部署 OpenCUA 7B/32B/72B 的视觉模型服务；模型大小由 GPU 条件决定。
   官方说明：https://github.com/xlang-ai/OpenCUA/blob/main/model/README.md
   7B 示例：vllm serve xlangai/OpenCUA-7B --trust-remote-code --served-model-name opencua-7b --host 127.0.0.1 --port 8000 --max-model-len 32768
   此命令仅为部署说明，本次没有执行。
3. 角色服务需具备多图理解和 JSON 指令遵循能力。role_model 可与 solver_model 相同，
   也可单独指定同一端点提供的视觉模型；当前示例名尚未验证角色输出质量。
4. 另存配置，填写实际单价、获准预算、模型服务，完成模型/VM 冒烟检查后开启 allow_live。
5. 将已安装 OSWorld 加入 PYTHONPATH，再运行：
   python -m python.run_osworld --task TASK.json --config CONFIG.json --run-dir runs/UNIQUE_ID --provider docker --vm-path DEDICATED_VM
   --vm-path 必须指向独立实验桌面；环境 reset 会进行题目初始化与快照恢复。
   解题仅传 instruction+screenshot；reward、DOM、evaluator 配置不进入任何角色。
   评分只在解题结束后执行一次，官方评分失败会写 result.json.error，保留已有轨迹。

主要文件
python/suz_agent.py          官方 OpenCUA 子类、角色调度与完成门控
python/visual.py             前后截图测量、局部放大、红叉副本生成与来源标识
src/visual-warnings.mjs      条件化区域经验、撤销、过期和重新定位
src/controller.mjs          原 HLD 记忆/规划接入、视觉证据和验收账本
src/prompts.mjs             桌面视觉角色协议
src/rpc.mjs                 Python 与 Node 的单题隔离进程桥
python/runtime.py          全角色计费、取消/限额停止、传输与持久化
python/run_osworld.py       官方环境运行与独立评分入口
python/offline_demo.py      五角色闭环的脚本化演示
VALIDATION.txt             本次验证结果及范围
