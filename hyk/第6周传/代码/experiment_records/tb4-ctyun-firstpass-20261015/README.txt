2026-10-15 Ctyun prepaid exploratory first-pass campaign
Model: deepseek-v4-flash-0428. Endpoint: https://ai.ctaigw.cn/v1/messages
Arms: KZ 0.3.0 evidence-control-1 integrated with DSH 0.2.0-rc.2; pure DSH from identical runtime.
First ten tasks in the previously frozen TerminalBench 4.0.0 order (commit 452bf305c6daa62fc59061d22133a7cbc7c1572e).
One attempt per arm/task per launch, two concurrent arms; no automatic paid trial replay. User-authorized continuation after the provider-usage stop retains the interrupted pair and charges in an archive, then starts from the same first task. Scores do not drive prompt or task reselection.
Each task first receives two unpaid installation checks. Original task resources, user, workdir and separate official verifier retained.
Shared durable budget: 30 CNY of prepaid package value, at 89.90 CNY per 100 million input+output tokens, including cached input. Maximum 33,370,411 tokens. Every provider attempt, including protocol probes and retries, reserves the full model input ceiling plus output before transmission. Missing usage retains the full maximum charge; at most one guarded retry obtains a separate reservation. No incomplete tool-call fragment reaches DSH. Prior actual and uncertain charges are never reset on continuation.
Stop all further paid admission and interrupt solvers on first official reward=1 with no verifier exception. In-flight calls remain reserved until settled. Official grading and cleanup continue.
Three-hour external solver deadline per attempt. Infrastructure and official grading retain original deadlines. No task answer or verifier feedback is injected into solvers.
This is an exploratory first-success run, not an unbiased benchmark estimate; the other arm may be censored by the first-pass stopping rule.
Credential is delivered through SSH stdin and held in process memory. No key is stored in this directory. Only the purchased model is authorized. No purchase, renewal or on-demand enablement.
