# Paired six-task repair-v2 pilot, 2026-09-29

User authorization: run six tasks for each of HAI and BestFGS. This new pilot uses
the first six entries of the existing seeded twelve-task manifest, without any
outcome-based selection. Both methods receive exactly the same six tasks, model,
official task inputs, image identities and task-specific budgets. No prior result
is carried forward, pooled or overwritten. This is exploratory, not evidence of
statistically established algorithm superiority or an isolated causal ablation.

The tested method sources are exact copies from mechanism-conversation-fix-v2:
BestFGS real multi-turn context and recall, HAI memory/scope repairs, and repaired
Docker/audit helpers. The shared official transport combines the prior lean
BestFGS adapter with the repaired HAI observation_cwd mapping. HAI terminal
classification delegates to the exact repaired classifier. These are deployment
changes; no new model policy is introduced for this pilot.

Model: deepseek-flash, https://api.deepseek.com, thinking disabled, temperature 0.
Main max output: 4096 tokens; BestFGS advisor max output: 1536 tokens, at most six
advisor calls. Retain 800 logical rounds, 600 tools, 900-second command limit and
the original API attempt ceilings. BestFGS retains its 48000-character context
budget; the methods' other existing settings remain unchanged and are hashed.
Use the original official wall budgets: spot-scheduler 10800 seconds, the other
five tasks 3600 seconds each. Reserve 120 seconds within each agent budget for
delivery. Original verifier budgets and binary same-conversation continuation
remain unchanged. Official reward, not model submission or local tests, is the
success metric. Record infrastructure errors separately from task failure.

Two global concurrent slots, with each task's two arms queued next to each other.
At most two active trials reserve 8 CPU and 16 GiB including candidate containers.
Disk admission floor is 120 GiB; execution hard floor is 60 GiB. Stop admission on
credential/balance errors, changed source hashes or repeated infrastructure errors.
Never automatically replay a trial. Scheduler recovery may only reattach live
workers or dispatch as-yet-unstarted jobs.

Before launch: verify images and exact repaired method hashes, run local harness
regressions and both real-Docker official continuation fixtures with scripted
actions (no model API), then seal all source, task and job hashes. Credentials
enter via hidden stdin and live only in restricted tmpfs, never in task containers
or logs. A catalog check precedes paid calls; credentials are deleted on terminal
completion. Previous source releases and experiments remain untouched.
