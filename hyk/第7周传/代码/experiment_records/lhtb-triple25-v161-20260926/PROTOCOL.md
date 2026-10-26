# LHTB three-arm file-artifact pilot: 12 tasks x 3

Directory retains its old `triple25` name; only manifest's fixed 12 tasks run.
Same tasks, image digests, task timeouts, tool limits and model in all arms.
BestFGS 0.16.1 collaborative graph; HAI 0.4.0; Raw uses HAI runtime with component disabled.
Model: deepseek-flash, official endpoint, thinking disabled, temperature 0, max output 4096.
Max action turns/graph iterations 800, executed tools 600, individual command 900 s.
Additional BestFGS assessment/memory calls count toward API/token cost, not hidden in action rounds.
Three concurrent trial slots, each reserves two 2-CPU/4-GiB containers (12 CPU/24 GiB total).

Official pinned Harbor same-conversation continuation; only binary rejection is exposed.
No hidden tests, reward files, controller keys, Docker socket or host paths enter agent branches.
Final success comes from official verifier rewards, never the agent's submit claim.
Task subset only covers synchronous file artifacts under /app, not live services/process restoration.
Rootfs snapshots preserve branch package/filesystem changes, not running processes.
Grading receives /app artifacts, not arbitrary branch OS package changes.
External symlinks in host evidence mirrors are refused rather than read on the host.
120 seconds of each official wall budget is reserved for delivery; setup is separately bounded.

Audit: hash-chained model prompts/responses, errors, tools and outputs; memory/runtime records;
graph selections/checkpoints; official result reports; source/task/image hashes. Output truncation
follows common execution limits. Fixtures validate continuation transport, not algorithm quality.

Metrics: official success over all fixed tasks, plus separately reported infrastructure exclusions;
action-model decision rounds, auxiliary model requests, executed tool calls, tokens and elapsed time.
Mean rounds must report both all runs and paired jointly successful tasks to avoid early-failure bias.
Tool redundancy is NOT command-string repetition. Tool calls remain `unreviewed` until a shared,
method-blinded evidence audit judges whether a call duplicated already valid evidence without a
state/dependency change or reasonable verification purpose. Report ambiguous labels separately;
do not silently report an unimplemented semantic redundancy metric as zero.

No automatic rerun of completed/failed trials. Scheduler heartbeats every <=30 s while waiting.
Detected model/adapter/infrastructure errors stop new dispatch; already active trials finish within
their bounds. No unlimited retries. Low disk (<60 GiB free) also stops dispatch/mutations.
Snapshots and logs retained; no shared-host prune. Completion with errors is `needs_attention`.
No desktop recurring monitor is created. Cloud tmux survives client disconnection, not node failure.
