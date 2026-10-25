LATS 六题修复补跑 — 2026-10-08

新目录：/var/tmp/lizh639-lats-recovery3-six-20261008
来源：/var/tmp/lizh639-longcli-lats-taco-recovery2-20261007/lats
只重跑 cmu15_445_p0、cmu15_445_p1、ap1400_2_hw35、61810_fs、61810_lock、61810_traps。
14 题已完成评分保留；旧失败记录保留。TACO、DH 不启动、不修改。
6 并发；deepseek-flash、thinking disabled、temperature 0；沿用 800 请求/600工具、
1600 wire 尝试上限、4096 输出 token、48000 字节输入上限、7200 秒单题时限。

修复：
1. 使用本地最新 repair_runtime.py，不再从服务器旧总目录覆盖修复版本。
   install('lats') 确实接入 Sandbox.execute，所有解题和价值评估验证命令均归一化
   timeout_seconds 至 1..300 秒。argv/cwd/stdin 和搜索逻辑不变。
2. 两题的四份真实坏响应都是完整 JSON 对象后多一个 }。
   json_transport.py 只接受这一种无歧义外层修正，不改任何解析字段/命令内容。
   不补截断 JSON，不选择多个对象，不猜测转义，不从自然语言或 Markdown 抽取。
   非法格式仍按既有最多两次格式尝试处理，所有请求计入原预算。
   每次确定性修正有 json-normalized-NNNN.json，不额外请求模型。
3. 上传文件 SHA 固化、启动前再次逐文件校验；验收调用实际 install 分发和真实
   Docker 执行器，以 600/700 秒请求确认归一化确实生效，并检查快照恢复。
   四份脱敏历史坏响应原样回放，逐字段核对修正前完整对象与解析值一致。

验收：accept_recovery3.py（零模型 API），启动：Start-LATS-Six.ps1（本地隐藏输入）。
密钥只经加密 SSH stdin 和匿名管道进入进程内存，不写参数/文件/日志。
已有题目不继承工作区或中间记忆，新六题为独立新尝试，不是树状态断点续接。
官方评分在学院服务器独立运行，不向解题器回传隐藏评分。
