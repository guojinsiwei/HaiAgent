# SWE100 paired experiment recovery and health policy

Installed 2026-09-18 after an observed transport/DNS failure. This is operational
supervision outside the frozen experiment implementation, not an algorithm change.

## Frozen assets

- Project: `/mnt/lizh639/BestFGS-compare-v4` (do not edit during execution).
- Output: `/mnt/lizh639/bestfgs-runs/swe100-paired-v2`.
- Protocol SHA256: `8ed0e6c5e01e920a7c3b2065ae5a1e269e622578c9fc469753ffb7738f350f9d`.
- Worker 0 on `lizh639-aa91`; worker 1 on `lizh639-8e64`.
- The same 100 IDs, model, fixed budgets and metric definitions remain in force.

## Recovery semantics and limits

`paired_health_guard.py` resides in `/mnt/lizh639/notebook-tools`, outside the frozen
project. Each guard polls its worker every 30 seconds. It adopts an existing live
runner without interrupting it. A per-worker guard lock and original experiment
worker locks prevent duplicate execution.

Only a terminal `search_error` whose last failure is an explicitly recognized
transient transport failure may trigger automatic `--retry-infrastructure`.
Before relaunch the guard checks API authentication/model availability, the full
protocol fingerprint, disk space, active runner and orphan agent/notebook processes.
The runner then checks seed and package fingerprints before executing the task.

- At most **3 total attempts per method/task**, including the original attempt.
- At most **20 guard recovery launches per worker**, persisted across guard restarts.
- Network preflight failures back off from 60 to 600 seconds; no paid task is
  launched until preflight succeeds.
- Completed attempts are never rerun, including unsuccessful solutions or malformed
  model output that the frozen runner classified as a completed model failure.
- Invalid credentials, billing/request errors, changed code/environment, unknown
  failures, orphan processes or exhausted recovery limits require human attention.
- A log unchanged for 30 minutes is flagged, not forcibly killed. The frozen
  per-task 4-hour timeout remains in force.
- Logs are appended. Prior attempts, patches, token usage and costs remain recorded.
- A recovery starts a new attempt from the seed, **not** from the last action.
  Retried tasks are explicitly marked `attempt_count > 1`; the existing comparison
  reporter excludes them from single-attempt efficiency comparisons and discloses
  incomplete single-attempt evidence. Do not claim the batch is entirely single-run.

## DNS intervention

Both notebooks retained their original cluster nameserver and search list, with
only `ndots:5` changed to `ndots:1`. Diagnosis before the change reproduced 10-second
delays and intermittent lookup failures. Immediately after the change both hosts
passed 3/3 fresh lookup probes. This is evidence of improvement, not proof that the
platform's DNS is permanently healthy. No fixed API IP or disabled TLS was used.

Audit and recoverable originals:

- `/mnt/lizh639/notebook-checks/dns-lizh639-aa91-20260918T154531Z/`
- `/mnt/lizh639/notebook-checks/dns-lizh639-8e64-20260918T154535Z/`

Record this infrastructure intervention time when interpreting network/wall-time
metrics. Kubernetes may recreate `/etc/resolv.conf` if a notebook is restarted.

## Inspect from local PowerShell

```powershell
ssh cubestudio_container "cat /mnt/lizh639/bestfgs-runs/swe100-paired-v2/health/worker-0.json /mnt/lizh639/bestfgs-runs/swe100-paired-v2/health/worker-1.json"
ssh cubestudio_container "/mnt/lizh639/envs/bestfgs/bin/tmux -L bestfgs-health-v1 list-sessions"
ssh cubestudio_container2 "/mnt/lizh639/envs/bestfgs/bin/tmux -L bestfgs-health-v1 list-sessions"
```

After a recovery the experiment can be a child of the guard rather than a separate
`worker-*` tmux session. Use actual `run_comparison.py` processes plus fresh health
JSON, not presence of the old tmux session alone, to establish liveness.

Health data: `health/worker-{0,1}.json`, `health/events-{0,1}.jsonl`,
`health/guard-{0,1}.log`. Heartbeats must remain fresh (usually less than 60 seconds).
`running` means alive, not solved. `waiting_for_network` is an automatic backoff;
`needs_attention` and `running_stale_log` require investigation.

## Monitoring limits

The cloud guards are detached tmux processes and keep working if the user's PC or
SSH connection closes. They cannot survive container deletion/replacement or repair
cluster-wide outages. No remote notification channel was configured in the guard;
it records attention states in persistent shared storage.

An app heartbeat named "SWE100 双机实验健康巡检" (id `swe100`) checks every 10 minutes
and only reports actionable changes/completion. It depends on local app/SSH access;
PC shutdown can delay notifications but not cloud-side recovery. It must not bypass
the guard limits, modify experiment settings or start official grading automatically.
