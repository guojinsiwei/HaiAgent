DSH / Recuris-Frozen-on-DSH / TACO-Local-on-DSH
2026-10-13 迁移候选版，版本 0.1.0

结果
----
两个独立插件已实现：../recuris-dsh、../taco-dsh。
本目录提供共同宿主依赖、配置、HTTP/工具审计、配置准备与离线测试。
未修改旧项目、实验记录或 kz-dsh；未调用真实模型、使用任务密钥或部署云端。
范围按用户确认：历史 frozen Recuris + 题内演化 TACO，明确是适配变体。

已通过：15 项 Node 验收（官方生命周期、原生真实 bash、真实会话压缩、
官方 DeepSeek HTTP/SSE 适配器与异常路径），10 项 Python 算法单测。
Windows 和 Linux 均通过上述 15 + 10 项检查。Linux 的三组生命周期又分别在
三个全新、无外网、只读容器中验收；另有两容器的工作区/home 隔离检查。
Windows 证据见 audit/latest.json；Linux 见 audit/linux/results.json、
python-results.json 与同目录日志。历史失败报告保留，不覆盖失败证据。
离线通过只证明机制与接线，不证明真实模型采纳、效果等价或效率收益。

仍需用户批准后的真实模型小测；目前没有算法有效性或效率收益结论。
本地 Linux 镜像 dsh-baselines-offline:20261013 已构建并验收，固定 ID、
Node 官方校验和、Python wheel 哈希及已测源码见 environment-lock.json。
构建时只下载公开依赖；运行验收时无外网，模拟 HTTP 服务位于各容器自身。

源码与历史证据
--------------
Recuris 作者仓库 https://github.com/Gen-Verse/Recuris
作者快照 7d3745ab787b1206ccd981cb1511100476097266，见 ../recuris-dsh/vendor/upstream。
实际历史算法：experiment_records/longcli-recuris-frozen-small20-20261007/recuris/src/recuris。
后续运行配置：longcli-recuris-large20-20261009/protocol.json、source-provenance.json；
协议恢复依据：longcli-recuris-protocol-repair4-20261009/io_repair.py、README.txt。
历史本来就是 LongCLI 解释实现：动态 W/严格实际验证，比作者 tb21 runtime_bridge
的单初始任务项/有界启发式完成检查更强；本次不能冒称作者 tb21 逐行复刻。

TACO 作者仓库 https://github.com/multimodal-art-projection/TACO
作者版本 2b048988e77ea67e6165450c97ebe66ce23a033f。
实际模块与锁：experiment_records/longcli-lats-taco-small20-20261007/taco_native、
source-provenance.json；后续 large7 的 README/protocol 明确每题无学习缓存。
作者机制与历史接线均核读；网站仓库已核对，固定版本依靠本地来源清单逐文件
SHA256 校验。未把目录名、聊天描述或不同名的 TACO 算法当作源码证据。

DSH 官方仓库 https://github.com/deepseek-ai/deepseek-harness
实际依赖与 KZ 宿主对齐为 @deepseek-ai/dsh 0.2.0-rc.2。
官方 npm 元数据无 gitHead，因此锁发布包 integrity、package-lock 和 14 个
关键宿主包的发布源码哈希。不能用本地历史目录的 5badb150（0.2.1-alpha.1）
冒充 rc.2 源码提交。source-lock.json 是本次可复核的版本/源码/配置锁。

迁移清单（原机制 -> 原源码 -> DSH 接入 -> 保留情况/差异）
------------------------------------------------------
Recuris W 目标初始化 -> prompts.INITIALIZE / working.initialize -> agent/pre-step +
  ctx.llm.stream -> 保留历史 LLM 初始化及最多 8 个目标，移除旧 actor JSON 循环。
Recuris W 更新/C 提交 -> prompts.UPDATE / working.apply_proposal -> tools/execute ->
  每次实际工具观测触发更新；只有真实、当前版本、匹配目标的验证回执可完成。
Recuris E/rho -> memory.invoke / terminal_seed.json -> pre-step 持久消息/上下文 ->
  种子配置是 first_turn + all，注入作者 terminal_closed_loop 通用卡；函数中的
  状态检索策略原样保留。没有私自新增运行时经验生成或 KZ 记忆策略。
Recuris Meta/TTA -> 作者 metaagent / tta/driver.py -> 本轮不挂载 -> 用户确认关闭。
  不进行训练集演化、同题官方反馈后重试或跨题迁移；不得称为完整论文收益复现。
TACO 规则规划 -> compression/planner.py -> 首次 pre-step 辅助角色 -> 保留。
TACO 规则过滤 -> output_filter.py / dynamic_filter.py -> 原生工具最终内容接口 ->
  原样复用过滤器；原始输出、退出码、权限结果另存且不被重写。
TACO 第二层模型压缩 -> filter_prompts.py + 原 _smart_compress 分支 -> ctx.llm.stream ->
  保留安全标志判定；辅助模型请求和用量照常计入。
TACO 未覆盖输出/投诉/演化 -> feedback.py / evolver.py -> 输出后及下一动作前 ->
  保留 spawn_new、冻结/替换、信心提升；恢复原文后未执行的旧动作交还 DSH 重决策。
TACO 全局池 -> rule_cache.py -> 每题独立 worker 内存 -> 关闭跨题池，明确适配变体。
子目标：仅 Recuris 有 W；TACO 没有，不添加。共同关闭原生 todo/goal 元数据工具，
  避免两个互不相通的目标列表。原生 DSH 组因此是共同约束下的 DSH，不是出厂默认。
多角色：Recuris 初始化/更新角色、TACO 压缩规则相关角色都保留；同一模型路由。
搜索/回溯：两条所选历史执行链都没有，未增加。没有 KZ 正交门控/Monitor/Advisor。
大小模型分工：所选历史配置没有强制大小模型区分，不添加。
工具/skill：DSH 执行原生工具；Recuris E 卡不是外部 skill 安装；TACO 不生成解题 skill。

明确的适配差异
--------------
1. 旧历史 12 对上下文/定长观测裁剪由共同 DSH 上下文、spill 与压缩取代；旧循环、
   终端驱动、模型客户端不再运行。三组共享宿主同一份配置。
2. Recuris 的 verify 改为 recuris_verify(goal_id) 委托原生 bash，稳定绑定目标，
   不要求所有动作先做策略声明。普通检查的文字相似度不用于伪造 done；模型可修订
   目标检查后实际重跑。已执行其他可能变更状态的原生动作会保守重开完成状态。
3. DSH 返回超时、取消、后台/截断等不完整回执时，不提交 Recuris 完成。
   历史已保存的回执不会因为不在最近窗口而删除；版本变化后旧回执不能证明现在完成。
4. TACO 的 dynamic_ 名称映射为原裸规则 ID，沿用历史修复，使投诉确实冻结对应规则。
   公共任务全文额外传给每个辅助角色，作者提示里的短任务摘录只作摘录，不替代全文。
5. TACO 未覆盖阈值使用作者主程序参数默认 3000 字符；历史 CLI wrapper 曾调用
   FeedbackCollector 默认 5000。此参数差异已显式保留在代码/测试，未冒称历史逐字行为。
6. TACO 读取 DSH 真实退出元数据，对失败或不完整观测保留原文；不据此制造投诉。
   原作者错误保护主要靠文本检测，这是适配 DSH 结构化工具结果的保守差异。
7. TACO 原 parser 对不可解析规划可能返回空规则，模型失败则回退种子；两种原行为
   都保留，同时把解析/接口故障标为工程降级。并未为追求测试通过替换成更强算法。
8. 按历史命令边界，三组共同禁后台 bash/超时转后台、委派 Solver、联网工具、外部
   skill 发现、自动标题模型。保留原生文件/搜索/终端工具和宿主权限管理。
9. 不支持进程崩溃后隐式恢复算法 worker。若已有 audit/run.json 则拒绝复用，须单独
   标记未完成工程运行；不把丢失的运行期记忆伪装成恢复成功。会话压缩不重启 worker。

预算与隔离
----------
config/common.json：历史 deepseek-flash，temperature=0、输出 32768、1M 上下文，
65536 headroom；800 次实际 HTTP 尝试、600 次工具、7200 秒、命令 300 秒；2CPU/8GiB。
模型 ID/端点可用性尚未在线验证，不代表今日服务承诺。三组都应用同一模型与资源。
按 transport fetch 入口计请求；辅助角色、DSH compaction、重试无例外。
stream 次数与 HTTP 次数分别记录，未知 usage 明确计为 unknown，不当作零成本。
每条 HTTP 记录只写来源/路径，不写认证头；每条使用量保留原宿主 usage。
原生工具与算法元数据分别计数；recuris_verify 自身和它实际委托的 bash 都计入。
任务时间在派发边界检查，在途终止由 DSH 的原生超时/取消负责，不增加强杀协议。
未定价格或钱数预算；与 KZ 真实对照前必须统一它目前独有的货币上限/禁用项，不能
拿旧 KZ 成绩直接比较。KZ 项目本轮保持不变。

运行一题一进程、一容器、一 workspace/home/tmp/session/audit、一算法 worker。
无全局缓存，无测试题间经验，无训练后冻结经验；只有作者通用种子，来源锁定。
本轮只有离线临时目录和无网络容器；后续实际任务也必须准备全新容器，不能共享
可写的源任务挂载、home、会话库、规则目录。父级完整工作区和其他任务密钥不可挂入。

复核命令（在本目录运行；不要运行真实模型）
----------------------------------------
node scripts/verify-lock.mjs
node scripts/audit.mjs
  Python 默认使用本机已安装的 Codex bundled runtime；可用 BASELINE_PYTHON 指定。
  Windows 沙箱若禁止 localhost，需允许这一次本机离线测试；无需 API key。
./scripts/container-check.ps1
  只用现有 longcli-audit/make-pytest 镜像，缺少时直接报告，不自动拉取。
./scripts/linux-check.ps1
  使用现有已验收镜像，在三个独立容器及另一个回归容器运行官方生命周期。
  environment-lock.json 固定镜像 ID，不能只凭可变 tag 认定环境相同。
  Linux Python 单测证据见 audit/linux/python.txt；入口为容器内
  /opt/python-dsh tests/algorithms.py，同样使用 --network none 与只读根目录。
  重建脚本 scripts/build-context-cached.mjs 使用本地已有公开 Node tar/wheels
  及缓存基础镜像；输入校验记录在 audit/linux-inputs.json 和 environment-lock.json。

准备未来三组小测（只生成，不启动）：
node scripts/prepare.mjs --task config/smoke-task.txt --out .runtime/my-prepared-run --python ABSOLUTE_PYTHON_PATH
node scripts/dump-prepared.mjs .runtime/my-prepared-run
  三组各有独立 manifest、workspace、home/audit 路径；共同配置 hash 相同。
  DSH 自己生成新 session；不误用只允许续接旧会话的 --session-id。
  manifest 中保留官方 headless argv，但没有自动执行器，offline=true 禁外部模型请求。

待你确认后的真实小测方案
----------------------
使用已冻结、已测的 Linux runtime（Node 24.9.0、DSH rc.2、Python/pydantic），
选 1 个公开小任务，核对起始文件和该任务所需原生 sandbox 配置后跑三组各一次。
如任务需要新增运行依赖，则建立派生镜像、固定其 digest 并重做离线验收。
固定起始文件/任务/image digest、共用配置/源锁、2CPU/8GiB、同预算和新鲜凭据；
凭据只由用户为本次明确提供给宿主模型通道，算法 worker 和题目 shell 不继承。
先核对请求台账、辅助开销、实际工具结果和压缩状态，再观察是否完成公开任务。
此后才能决定是否扩展；不自动启动基准、追加尝试、改预算或继承其他测试题经验。

已知限制
--------
真实模型效益、长程模型行为及真实端点尚未验证。离线验收使用官方 DSH 生命周期、
原生本地 bash 和权限拒绝路径，不宣称覆盖生产 sandbox 后端的全部安全行为。
正则过滤/启发式反馈和公开检查的覆盖缺陷来自原方法，不等于隐藏测试正确性证明。
TACO 只自动恢复最近一次压缩原文；更早原文保留审计，不假称已重新检索给模型。
Node 依赖从 KZ 的已安装公开 DSH 依赖复制到独立目录，未复制 KZ 算法或密钥。
离线 npm cache 不完整，npm ci --offline 曾失败；Linux 镜像已按 package-lock
成功执行 npm ci 并通过验收，未把 Windows 原生依赖当作 Linux 安装。
