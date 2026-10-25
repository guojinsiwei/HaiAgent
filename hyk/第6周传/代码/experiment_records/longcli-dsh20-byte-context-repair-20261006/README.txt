DSH byte-context repair candidate, 2026-10-06. Not a launched experiment.

Preserves official DSH 0.2.0-rc.2 solver prompts, tools, native read-before-write
bookkeeping, replay and compactRegion durable summary transactions. Does NOT
add DH memory, orthogonality gates, route search, advisors or forced edits.
This is DSH + a modified experimental context adapter, NOT untouched official DSH.

Fixes the former 8000-token pressure/zero raw-tail adapter. Pressure admission now
uses a conservative projected UTF-8 messages+tools envelope at 42000 bytes,
including a 1024-byte plus per-message/tool margin. The exact 48000-byte relay
guard remains authoritative and rejects overflows before any paid request.
It preserves at least 4096 bytes of recent complete tool groups, and only
summarizes a balanced older prefix of at least 5000 bytes. Native result pruning
precedes summary generation on OLDER tool results only, protecting the recent
raw tail. Only if fixed overhead plus the recent raw group and a short checkpoint
reserve still projects >=48000 bytes, native full-surface pruning is the bounded
fallback; this exception is separately audited. One summary transaction per step; no loop
that immediately recompresses the checkpoint just written. Summary errors are
now audited rather than recording only start/end events.

Summary directive is replaced, not appended to conflicting "no loss" instructions.
Eight native headings retained. Target 180 words; requests <=300 words and
2500 UTF-8 bytes. These are SOFT model instructions; oversized real summaries
are recorded, not silently cut, retried for free or claimed impossible.

Unchanged: deepseek-flash, thinking off, temperature 0; 800 logical model requests
including compaction/title, 1600 wire attempts, max two per decision; 600 root
native tools; 4096 output tokens; 48000 UTF-8 input bytes incl tool definitions;
24000 observation bytes; command 300 sec; AP26/AP35 3h, other trials 2h;
historical Cube frozen rootfs, two CPU cores, 3GiB address space per process;
fresh rootfs/HOME/session/workspace for each task; no cross-task memory, task
network or hidden tests during solving. Original DH/RAW and prior DSH preserved.

Keyless acceptance: native basic isolation, adversarial large four-tool batch
pressure (129 tools), and moderate long-context pressure plus long-file read
(194 tools). Must show
actual committed summaries, early evidence used in a real subsequent edit,
the recent long-file MIDDLE still visible after a native read, no provider-side
history removal, and moderate
output not causing a summary each step. These fixtures do NOT prove score gains
or real-model avoidance of read loops. No paid trial launches during acceptance.

Known comparison limitations remain: DSH native tool interface/process model
differs from DH/RAW; DH historically bounded characters rather than bytes.
Do not claim strict tokenizer-budget equivalence or guaranteed superiority.
Fresh local hidden key is required for an explicitly authorized paid retest.
