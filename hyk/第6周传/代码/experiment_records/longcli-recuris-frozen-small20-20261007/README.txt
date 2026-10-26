Recuris-Frozen, LongCLI20 matched small budget, 2026-10-07.

Human explicitly requires NO official feedback and SAME configuration as LATS/TACO.
One independent attempt per task. Fixed unlearned terminal seed; no Meta-Agent,
no TTA, no cross-task learning, no result/hidden-test/score passed to the solver.
Do not call this a full reproduction of Recuris-TTA or learned memory evolution.
The handoff's unmodified memory, invocation, W-proposal and fixed C/K validation
are retained. Runtime W state changes within a task, but memory M remains fixed.

Same 20 pinned starters/images, final unmodified official grader, deepseek-flash,
thinking OFF, temperature0,4096 output tokens,48000 UTF8 message-envelope bytes,
800 logical model calls INCLUDING initialize/actor/W-update/format repairs,
<=1600 wire attempts,600 tools,300s command cap,2h ordinary/3h AP26+AP35,
2CPU,8GiB aggregate,3GiB HARD command address space,128 PIDs, no solver network,
read-only root, no credentials/socket/hidden tests mounted, fresh shell each command.
No free-space or total snapshot admission threshold, per the user's instruction.

The original package's native tmux adapter is NOT used: its interactive/persistent
terminal and default120k-char/450-call/200-step budget would differ from other arms.
The isolated adapter changes only context metering/projection, command transport
and verification receipts. Complete shell scripts/heredocs are supported. Duration
is compatibility metadata; every command completes or is stopped by the same300s
upper bound. No interactive keys/background jobs/polling. Public check receipts
are actual process-driver exit codes, with same goal ID/check digest/state revision;
model claims cannot fabricate completion. All raw command evidence is audited.
Native200-step cap becomes800 so the common all-role800-call budget binds instead;
history12 and10 consecutive public check errors remain intrinsic method parameters.

The zip and54 manifest-listed files are pinned and verified. Modules remain verbatim
under recuris/. Source reference: arxiv2608.24876 and Gen-Verse/Recuris commit
7d3745ab787b1206ccd981cb1511100476097266; handoff is already a LongCLI migration.
No learned LongCLI skills/results were in the supplied package.

Deployment is separate from LATS/TACO:
/mnt/sdb/home/lizh639/longcli-recuris-frozen-small20-20261007
Two included graded canaries before full admission. At most2 simultaneous tasks
after canaries. Fail closed on engineering faults; no automatic paid task retry.
Launch requires fresh local hidden credential input after sealed keyless acceptance.
This request is adaptation/deployment; NO paid launch is performed without a
subsequent user instruction. Existing experiments and their credentials are untouched.
