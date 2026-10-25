# LHTB full paired run: preparation audit, NOT launched

Date: 2026-09-26. Candidate method: releases/collaborative-context-v16 (0.16.1).
Benchmark commit: d78f5eb52ad754c5ee9154741af73130a85a65b8.

## Verified inventory

- 47 actual task.toml files, not the README's 46; 31 set continue_until_timeout.
- 94 fresh trials for two arms. Previous three Raw diagnostics must not be reused.
- Configured agent time: 117 hours per arm, 234 total; 1–8 hours per task.
  This is a sum of configured budgets, NOT an elapsed-time or API-cost prediction.
- Agent environments request at most 4 CPU / 8192 MiB, no GPU.
- College node: Docker filesystem 262G free; /mnt/sdb 200G free at audit time.
  Shared host resources are not this user's allocation. Image sizes are not yet audited.
- Full machine-readable resource inventory: task-resources.json. No verifier secrets included.

## Launch blockers, with inspected evidence

1. Installed Harbor trial/single_step.py has no continue_until_timeout,
   _signal_agent_process_tree, or HB_VERIFIER markers. Official repository requires
   continuation plus verifier isolation. The full patched harness must be installed
   independently and tested; do not patch the shared previous-experiment runtime.
2. Old college cloud_agent.py runs as root and fixes cwd=/app. sudoku-recovery
   specifies agent user=agent; genetic-convergence-testing has /root artifacts;
   snake_maze_campaign, sudoku-recovery, unknown-config-semantics have /opt artifacts.
3. Old container_runner.py snapshots/delivers /app only. Live service/game state is
   not branch-restored. BestFGS graph branches cannot be claimed independent with
   this adapter. Need an explicit environment-state strategy before all-task launch.
4. Old container_runner.py rejects an existing run root and has no continuation
   handoff; it cannot be re-invoked unchanged for official continuation phases.
5. The current CLI is patch-delivery oriented. Non-code task submission and successful
   process termination need an adapter contract that does not mislabel empty patches
   or internal success as official results.

## Intended fair protocol (draft, not frozen)

- Same pinned tasks, base-model identity, API endpoint, environment images/digests,
  task user, network policy, command interface and per-task official time limits.
- Independent clean environments per arm, no cross-task memory or grader leakage.
- Retain current graph branching; do not silently replace BestFGS with HAIAgent.
- Action/assessment/memory calls all count toward method cost and API-call totals.
- Distinguish decision rounds, API requests and tool executions; log tokens, wall time,
  official reward/pass, and inspectable redundancy candidates with evidence.
- Bounded preparation retries, paired completion manifest and no reruns of ordinary
  model failures. Disk reserve required; do not pull all images blindly or prune shared Docker.

No full-run cloud directory, image batch, model call, or background monitor was started
by this preparation audit. No algorithm code or existing run was modified.
