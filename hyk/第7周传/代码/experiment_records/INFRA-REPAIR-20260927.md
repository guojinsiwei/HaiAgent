# 2026-09-27 infrastructure repair handoff

## Observed causes, not conjecture

- College `/mnt/sdb`: 93 GiB free (99% used shared volume); `/var/lib/docker` filesystem 242 GiB free at inspection. Not full. No data deleted.
- LHTB r2 stopped dispatch because HAI's final `model_error` followed by nested `method_end.result.stop_reason=wall_budget` was misclassified. All 11 completed trials have official verifier results and zero process exit codes. Their scores, including zero, are retained; 25 trials unstarted.
- Cube: intermittent DNS lookup failure independently observed. Historical HTTP wrapper recorded only `URLError`, so not all past failures can be conclusively called DNS failures. Old recovery policy also exhausted a lifetime six-recovery counter despite successful calls between failures.
- LongCLI Scheme r2 stopped with API error after 569 cumulative tools/rounds, no source revision changes, no official final grade. Prior active wall time totals 2220.689892122522 seconds across r1+r2. Original maximum 600 tools/800 turns/7200 seconds remains in force.

## Deployed repair revisions

College: `/mnt/sdb/home/lizh639/lhtb-triple12-v161-20260927-r3`.
Frozen protocol SHA256: `9ec2136c13cbe23b819ad8770b9e3b2a756217b071d1b1a1c35d27c45bc83915`.
Same benchmark/method sources, model, task list and budgets. Fix terminal classification;
carry 11 validated official reports; only dispatch 25 unstarted trials. Disk below 60 GiB
pauses new dispatch. Separate durable trial processes, PID/start identity reattachment,
exclusive launch intents, scheduler guard up to three restarts. Missing/ambiguous trial
processes stop for inspection, never replay a task blindly.

Cube: `/mnt/lizh639/longcli-raw3-20260927-r3`.
Same Raw model/prompt/tools/budgets. TLS-host-preserving DNS cache and multi-address
connect fallback. Detailed safe transport stage/type/errno logging. Retry episodes capped
at 900 seconds and eight extra cycles within original task deadline, not a lifetime limit
of six transient incidents. Certificate/auth failures are not given extra recovery cycles.
Separate trial process and scheduler guard; sequential three tasks. Reconstruct the 569
recorded exchanges without tool/model execution, assert exact next context (except remaining
budget values and host workspace spelling) and final workspace fingerprint, then continue.
All earlier trace files and exported artifacts remain untouched in their old revisions.

## Executed zero-call validation

- College: 8 classification/durable-ledger unit tests passed.
- College: killed a synthetic scheduler and started a replacement; same two trial PIDs
  completed, zero duplicate starts, zero real API/Docker operations.
- Cube: 7 DNS/cache/TLS/multi-address/recovery/auth tests passed.
- Cube: full 569-exchange replay passed; 0 model calls and 0 tool executions, exact next
  context and workspace checked. Evidence: r3 `repair-checks.json`.
- Cube: synthetic scheduler-kill/replacement drill passed; same trial PID completed,
  zero duplicate starts, zero real API calls.
- Combined PowerShell launch script parsed successfully.

## Actual start status at handoff

Both revisions were deployed and readiness-checked, but **not yet launched**: previous
controllers removed their private credentials on exit. No unrelated credentials were read.
User must privately enter their key through `Resume-TwoExperiments.ps1`, once for both;
college launches first. Already-started healthy jobs are skipped. Then inspect actual
health, trial processes, API events and result production before claiming live recovery.

No desktop/GPT polling automation was added. Detached tmux guards survive local shutdown,
not server reboot, OOM or loss of all storage. Runtime credentials exist only in protected
`/dev/shm` files and are deleted when their guards finish. Recovery is bounded; no promise
of perpetual uptime. Completed model trials are not restarted. Repair versions and all
recovery/API attempt costs must stay explicit in later scientific reporting.
