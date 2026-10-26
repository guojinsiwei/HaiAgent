# Frozen paired run (2026-09-18)

- Master plan: `/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen/task-plan.json`.
- Prepared root: `/mnt/lizh639/bestfgs-runs/swe100-reserve-v2/frozen`.
- Release: `/mnt/lizh639/BestFGS-compare-v4` (do not edit during the run).
- Shared output: `/mnt/lizh639/bestfgs-runs/swe100-paired-v2`.
- Worker 0: `lizh639-aa91`; worker 1: `lizh639-8e64`.
- Both use `--shard-count 2`; sort task IDs by SHA256 then alternate assignment.
- Each worker owns 50 distinct IDs, and runs BOTH methods per ID.
- All exports retain the same 100 expected IDs and identical protocol hash.
- Per-worker long-lived locks prevent duplicate runners; an NFS metadata lock
  serializes protocol creation and bundle exports. No automatic solution retries.
- A dedicated tmux socket `bestfgs-paired-v2` hosts session `worker-0` or `worker-1`.
- Logs: `worker-0.console.log`, `worker-1.console.log` in the shared output root.
- Worker status: `workers/0.json`, `workers/1.json`.
- Partial exports may contain pending tasks. Evaluate final bundles only after
  both workers complete and each arm has 100 terminal task states.
- Official Docker evaluation is a separate local-host stage, not started here.
- This changes dispatch only; no algorithm, task, model, budget or metric change.
