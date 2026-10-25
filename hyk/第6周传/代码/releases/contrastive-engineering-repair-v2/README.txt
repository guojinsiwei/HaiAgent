Engineering-only repair candidate, 2026-10-02. NOT DEPLOYED; NO LIVE MODEL CALLS.

Copied from frozen contrastive-exploration-v1. Original source, campaign and
results remain unchanged. No GPT background automation is created by this code.

Repairs:
- Advertise existing per-field character caps in both system and reserved tail.
- Distinguish too-long, empty, wrong-type and NUL review fields; report exact
  field, actual length, cap and a targeted shortening instruction. Do not claim
  a length failure means the strategy has no concrete change or verification.
- Feed structured review errors into the existing bounded action correction
  loop, with audit events. Keep request/tool/format budgets unchanged.
- Make the orthogonal final_command documentation agree with execution:
  accept the exact shell script or a shell wrapper whose parsed argv matches
  exactly. Similarity still uses the same executed command. No semantic
  similarity exemption, hidden repair or execution of malformed output.
- File-only command helper acts as a Linux subreaper and cleans its adopted
  children, including nested GNU timeout and setsid process-group escape. This
  does not change generic HAI executor behavior. Unrelated processes are excluded.
- Docker branches run with init for orphan reaping and use an immutable fresh
  init/sleeper baseline plus process state instead of raw process count. Zombies
  are not running daemons; actual detached live processes remain refused.
- Plain Python supervisor pauses new admissions after two ended tasks show the
  same shared review/wire/contrastive format fault. Active workers drain, ledger
  and original budgets are kept, and no task is replayed. Low reward, exhausted
  budgets, or legitimate unchanged-failure/similarity refusals do not trigger it.

Integration files belong beside a NEW campaign's adapter/control files, not in
the finished campaign. transport uploads process_cleanup.py together with the
command helper. The core candidate belongs in that campaign's common source.

No automatic replay, benchmark restart, credential reuse, extra paid model,
threshold relaxation, cross-task memory, route search, or output truncation.
Regression verification completed: Linux 160/160 passed with no skips; Windows
132 passed and 28 Linux-only tests skipped. Actual isolated Docker verified
timeout descendant cleanup, detached-launcher rejection, successful next action,
snapshot and delivery. Full results are in VALIDATION.txt.
Fresh-key live validation is still needed before a separately named benchmark
campaign. Offline passing does not prove real-model recovery or algorithm gain.
The original 24-trial campaign has NOT resumed; this release does not contain
credentials and cannot silently launch paid model work.
