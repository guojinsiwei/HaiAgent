# LongCLI: BestFGS v6 / RAW paired 10

This is an independent 20-trial diagnostic, not the earlier 120-trial plan.
It uses the pinned LongCLI commit `2015f37b5c458f2562354de6b415e9182c91af64`.
The ten tasks are selected by environment family (all five non-xv6 Python/Scheme
tasks and all five C++ tasks), not by model results. Each method gets the same tasks.

## What is actually compared

- BestFGS: frozen `releases/monitor-control-v6.1/sources`, i.e. the v6 algorithm plus
  its existing engineering fixes. No algorithm-module edits in this experiment.
  Memory, advisor, monitor, outcome reliability and stagnation control are enabled.
  The main actor, advisor and monitor all use the same DeepSeek model, with independent clients.
- RAW: the frozen HAI package's `method=raw` path, ordinary sequential CLI history,
  no memory block, advisor, monitor, memory intervention or branch restoration.
- Model: `deepseek-flash`, temperature 0, thinking disabled. Both arms use one JSON
  action per reply, avoiding a JSON-versus-function-call transport confound.
- Main output cap: 4096 tokens; v6 advisor/monitor retain their native 1536-token caps.
  Main/advisor wire attempts: 2; monitor: 1. All roles' usage must be counted.
- Tools: 600; logical model requests: 800; command cap: 300 seconds. Original task
  wall budgets: eight tasks 7200 seconds, the two AP tasks 10800 seconds.
- Native context policies remain part of the methods: v6 48000 characters with
  budgeted dialogue/memory, RAW 48000 UTF-8 bytes of sequential history. These are
  NOT equal token/byte caps and the experiment must not claim a context-only ablation.
- Initial instruction is the actual task.yaml entry point. Models read the complete
  public specification on disk; it is not duplicated or truncated in protected context.

Each of the two CubeStudio containers runs ten tasks sequentially: five v6 and five
RAW, crossed by task index. The paired method for a task runs on the other worker.
Concurrency is two, not twenty. Private task roots, histories, memories and checkpoints
are independent; the shared NFS directory is outside each command's chroot.

## Generation and grading

CubeStudio runs no Docker. Commands use a private export of the actual official
base image, low host UID, user/PID/network namespaces, dropped capabilities,
`no_new_privs`, 2-core affinity and per-process address-space/pid/file limits.
Only /app and /tmp are writable. Host /proc, shared NFS, keys and hidden tests are absent.
Each command has a fresh process namespace; persistent services are unsupported.
Only source-file tasks are in scope; no xv6 tasks or process-state tasks are claimed.

Sources are frozen before evaluation with a SHA-256 archive. Safe internal relative
symlinks and ordinary permissions are preserved. Import uses full replacement, so
deletions are retained; exact known build/cache directories are excluded, never broad
`build*` prefixes (which would incorrectly remove `build_support` source files).

Official grading happens once in a fresh owned Docker task image on BC-Server01.
It injects unchanged pinned tests and run-tests.sh, using the upstream metric helper.
Grading has 8 cores/8 GiB per container and a 100 GiB storage reserve. This is separate
from the identical two-core generation allocation, with original grading timeouts.
No hidden-test feedback is returned to either solver. Missing score/coverage, timeouts,
provider failures and infrastructure failures are not silently counted as task failures.
Completed/claimed trials are not automatically rerun.

This is split-environment, single-final-grading diagnostic evidence, NOT an
official leaderboard-equivalent LongCLI execution or an estimate with narrow confidence bounds.

## Acceptance and known caveat

Paid launch requires both ten-task solver preflights, official starter grading,
representative returned-artifact score equality and sealed source hashes.
Offline fixtures consume zero API calls and are not task performance results.
Prep failures are retained separately; none consume a formal trial slot.

Cats has an upstream starter defect: official P2P expects `READMD.md`, absent from
the pinned starter. It passes 18/19 protection checks before any model modification.
Keep unmodified official scores; explicitly flag the pre-existing failure and report
F2P separately. Do not infer that either algorithm caused that baseline failure.

## Start / progress

Run `Start-Paired10.ps1` in Windows PowerShell with process-local execution-policy
bypass if required. It asks for the API key using hidden input; do not paste the key
in this chat or add it to source/arguments. Authentication is checked on both hosts
before either worker is launched. Each worker keeps its own private tmpfs credential
and removes it at the end. A second launch is refused.

The laptop-side `relay.py` sends frozen sources to the college grader and retrieves
scores and logs. Keep this computer online while grading. Solver workers are detached
and continue without the laptop; artifacts remain queued if the relay stops. Do not
relaunch workers to restart grading. Recover/restart the relay after inspecting its logs.

Cloud: `/mnt/lizh639/longcli-v6-raw-paired10-20261001`

College: `/var/tmp/lizh639-longcli-v6-raw-paired10-20261001`

Status: cloud `health-0.json` and `health-1.json`; local `paired-status.json`.
Evidence: `preflight-*.json`, `grading-acceptance.json`, `roundtrip-acceptance.json`,
`ready.json`; full model/audit/generation/test logs retained per job.
