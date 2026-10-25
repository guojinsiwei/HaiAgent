# BestFGS memory-reliability-v5 twelve-task run, 2026-09-30

User authorization: deploy the current BestFGS and run twelve tasks on the cloud
server. Use all twelve entries from the original seeded manifest, in unchanged
order. One BestFGS trial per task; no HAI trials, no prior results carried forward,
no automatic replay. Keep all earlier experiment directories and releases intact.

Exact method sources and integration come from memory-reliability-v5. Explicitly
enable semantic_monitor, auto_memory and memory_reliability. This is the continuous
executor, not automatic graph search. Actor, advisor and semantic monitor use
deepseek-flash; monitor is an independent short-context client using the same
model/provider. No claim of a causal ablation or superiority from this run alone.

Model endpoint https://api.deepseek.com; thinking disabled; temperature 0.
Actor output limit 4096 tokens, advisor/monitor 1536 tokens. Preserve 800 logical
rounds, 600 tool calls, 900-second command ceiling, six advisor calls and twelve
monitor calls. All mechanism work counts against the same task wall budget.
Retain the release's API attempt ceilings and 48000-character context budget.
Reserve 120 seconds for delivery. Same-conversation binary verifier continuation;
official verifier reward is the success metric, not public tests or model claims.

Use original task wall budgets: spot-scheduler-traces 10800 seconds;
microscopy-cell-count-qc-audit, satellite-flood-change-detection-audit and
unison-paper-reproduction 5400 seconds each; remaining eight tasks 3600 seconds
each. Original verifier budgets, task contents and Docker image digests unchanged.
Total agent wall budget is 15.5 hours, scheduled across two concurrent slots.

Resource reservations include official and candidate containers. Disk admission
floor 120 GiB, execution floor 60 GiB. Stop dispatch for credential/balance faults,
changed sealed inputs or repeated infrastructure failures. Scheduler may reattach
live workers or dispatch unstarted jobs, never replay an attempted trial.

Before paid calls, verify all twelve image identities, method/integration hashes,
offline regressions and one scripted real-Docker official continuation fixture.
Seal source, task and job hashes only after passing. Credentials enter via hidden
stdin, are kept in restricted tmpfs, never placed in task containers or logs, and
are removed on terminal completion. The launcher checks model availability first.

Collect memory proposals/admission/rejection, repair reasons, retrieval/exposure,
use and outcome, semantic-monitor interventions, tool utilization and stop reason
alongside official reward. Mechanism activation is not proof of positive benefit.
