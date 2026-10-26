DH 独立子目标候选版（DH-subgoal-v1）
日期：2026-10-08

基线：releases/DH-recovery-repair，即 DH v9 最近一次恢复机制修复候选。
这里只新增 DH 子目标能力，不使用 HAI/terminal_context 的 SubgoalLedger。
没有修改冻结 DH、之前的实验代码或远端运行；没有部署或启动付费实验。

入口与开关
  保持 bestfgs.lean_runtime.LeanTaskRunner 入口。
  实验配置中显式增加 subgoals_enabled=True；False 为消融/原行为。
  lean_cli 也增加 --subgoals / --no-subgoals；不要为了此功能开启 route_search。
  一份符合 DH 正交分支的配置示例：
    LeanConfig(contrastive_mode='orthogonal', contrastive_predictions=False,
               memory_reliability=True, outcome_reliability=True,
               subgoals_enabled=True)
  其余模型、监控器、记忆开关及预算须沿用实际实验配置，此例不是新实验协议。

这版具体做什么
  1. 普通动作携带 subgoal_plan，不新增规划角色或独立规划调用。
     每次最多新增 4 项，单题总容量 12 项；不静默淘汰未完成目标。
     每项包括稳定 ID、名称、验收条件、前置目标、相关文件、检查命令和输出断言。
  2. 模型用 subgoal_id 声明当前动作所推进的目标；保留尝试次数和实际证据。
     上下文列出全部目标的状态和依赖，并给出可推进目标；优先维持当前可行目标，
     否则优先建议能解锁更多后续目标的前置项。不强行替模型执行动作。
  3. 只有声明后的真实工具执行，命令与固定检查一致、退出正常、输出完整、
     断言满足、前置项有效且相关文件在检查期间未变，才标记 check_passed。
     已实际运行的匹配检查立即计入，不为补一个 phase 标签重复执行。
     模型自报完成、工作区发生变化、普通命令退出 0、被门控拦截均不算验收。
  4. 相关文件变更或状态未知会使检查失效；失效传递到依赖它的已验收目标。
     显式恢复检查点后所有已通过项要求复检，不自动复活历史结论。
  5. 可以 blocked/deferred/pending，不允许模型直接写 check_passed。
     已定义的验收条件不可偷偷变弱。确需换标准时，明确搁置旧目标并定义新 ID。
     依赖环、未知 ID、容量超限等只让本次子目标元信息被忽略，不拒绝正常命令，
     不累计致命协议错误，不阻止部分交付。
  6. 子目标上下文最多 3500 字符。保留原记忆保护区，不增加原请求/工具预算。
     不会固定增加模型调用，但会增加提示词长度，不能称为零 token 开销。

动作示例（附着于普通 run，不是新工具）
  {
    "action":"run",
    "argv":["python","test_parser.py"],
    "subgoal_plan":[{
      "id":"G1",
      "title":"解析器满足公开输入规范",
      "acceptance":"空输入和正常输入均返回规范要求的值",
      "depends_on":[],
      "targets":["parser.py","test_parser.py"],
      "verification":{
        "argv":["python","test_parser.py"],
        "stdout_contains":["parser checks passed"]
      }
    }],
    "subgoal_id":"G1",
    "subgoal_phase":"verify"
  }
  test_parser.py 必须真正断言结果，不能仅打印成功标记。
  若启用原记忆审查，仍须遵守原 memory_review / strategy_adjustment 的字段顺序。

审计与可比性
  每题独立 subgoals.json；完整事件沿用哈希链日志。
  subgoal_defined / focus_changed / action_observed / check_passed /
  check_not_passed / invalidated / status_changed / metadata_ignored 可追溯到证据。
  result.json 增加 subgoal_summary 和 mechanism_utilization 中的 subgoal_* 计数。
  子目标改名不算可执行动作改变，不能绕过原排重/记忆门控。
  开关关闭时没有新提示、新目标状态文件或新目标统计。

边界（不能夸大）
  check_passed 只代表模型声明的局部检查通过，不等于子目标语义正确，更不等于
  官方任务成功。控制器不能证明自写测试覆盖充分，也不能阻止伪造的成功打印。
  文件依赖来自显式声明，未覆盖的动态依赖和外部状态仍未知。
  此版无自动回滚、无强制目标调度、无跨题记忆，不是新增图搜索算法。
  实测收益尚未验证。应在固定模型/题目/预算下比较开关两组，不能用单测声称提分。

验证
  python -B record_acceptance.py
  原有历史记忆回归使用 evidence/previous-rejected-candidates.json（仅测试夹具）。
  新增回归涵盖真实 Python 检查失败→修改→复检、误报完成、前置依赖、相关变更、
  回滚失效、门控拒绝、上下文容量、关闭开关及软错误不终止任务。
  evidence/subgoal-acceptance.json 为本候选实际执行的验收记录。

主要代码
  sources/bestfgs-project/src/bestfgs/subgoals.py
  接入：lean_runtime.py；开关：lean_protocol.py / lean_cli.py
  测试：tests/test_subgoals.py
