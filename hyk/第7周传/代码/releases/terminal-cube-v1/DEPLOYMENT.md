# Deployment record — 2026-09-19, Asia/Shanghai

User explicitly requested stopping the old run and restarting after shared-interface fixes.
Old v4 code and swe100-paired-v2 outputs remain preserved. Both old process trees and
old cloud guards were stopped; per-host stop records are in the old health directory.

- Local source: this directory (independent release, not an in-place Desktop overwrite).
- Cloud code: `/mnt/lizh639/BestFGS-compare-v5`
- Cloud results: `/mnt/lizh639/bestfgs-runs/swe100-paired-v3`
- Plan: `/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen/task-plan.json`
- Plan SHA256: `8e46676a0b79150c84a9fca745bed3638dd1f4f6e8bad6df4ca62405609affe7`
- Protocol SHA256: `7a01769a47fe0ab75a5edf830e05d1b3b6905df6baba3a9383f3189d9ea8d2e1`
- Implementation SHA256: `d7621862f883ca560a86772794036aeb77714ba13177517ac5b138c2a49a185f`
- Cloud guard: `/mnt/lizh639/notebook-tools/paired_health_guard_v5.py`
- Worker tmux socket: `bestfgs-paired-v3`; guard socket: `bestfgs-health-v3`.
- Same fixed 100 IDs, disjoint 50+50 sharding, both methods each task: 200 method runs.
- Guard retains max 3 attempts per method/task and max 20 recovery launches per shard.
  Completed model-output failures are never automatically rerun. No official evaluation started.
- Desktop heartbeat `swe100` was paused during maintenance, then updated to v5/v3
  and resumed. Desktop heartbeat needs the local machine; cloud guards do not.

Verification: 310 tests on Windows (5 skipped), 310 on cloud Linux (1 skipped),
10 guard tests; all passed. One tiny real DeepSeek JSON/SSE probe passed with no
task command execution. Both host API authentications and protocol checks passed.

At launch both workers produced valid parsed responses and executed CLI commands.
The new diagnostics also captured complete `finish_reason=stop` responses containing
DSML markup after JSON. These are rejected and syntax-only retry feedback is applied;
this does not establish that all historical failures had the same cause or eliminate
all future format failures. A successful first heartbeat is not a guarantee of uptime.
