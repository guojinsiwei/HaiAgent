Matched-resource official DSH-only LongCLIBench20 rerun

Historical DH and RAW results remain unchanged; the wide-context/32k-output DSH
campaign remains a separate unmatched result and is never merged into this run.

Model: deepseek-flash, thinking disabled, temperature 0. Native DSH 0.2.0-rc.2.
800 logical requests including native auxiliary calls, max two provider attempts
per decision (1600 hard wire cap), 600 root native tools, output <=4096 tokens.
No cumulative token ceiling existed historically; none is silently introduced.
Wall limits are copied per task: AP26/AP35 10800 seconds, other tasks 7200.
300-second tool timeout; historical frozen rootfs/public tasks on the same Cube
workers, two CPU cores and 3GiB address space per process; two tasks per worker.
Each trial has an independent rootfs, HOME, workspace and session. No cross-task
memory. No externally reachable task network or hidden tests during solving.

Remaining interface differences (not hidden): native DSH tools are retained;
DH/RAW used terminal commands and a strict JSON wire. DSH counts file/goal tools
within its 600 native root tools. Native DSH keeps a session process; historical
DH/RAW execute commands in fresh process namespaces. Input: DSH messages plus
native tools <=48000 UTF-8 bytes, using OFFICIAL DSH durable compaction;
historical RAW used bytes and DH used characters, so these are not identical
token budgets. Tool schema size is charged, rather than giving DSH free space.
Original failed matched run is paused and preserved separately. No results are
merged. The relay never silently prunes history; overflow is rejected before
billing. Native compaction triggers at8000 estimated tokens, summarizes the full
balanced older prefix (upstream still keeps its latest tool group) and produces
up to4096 summary tokens. Native result pruning retains
2000/1000-character head/tail above6000 characters, as durable session replacements.
Auxiliary calls count within800 requests. Keyless acceptance requires a committed
checkpoint AND use of early evidence after32 four-tool batches (129 tools), with
summaries deliberately larger than the failed1024-token cap. Only successful
compaction/summary events count; an ending marker alone does not prove commit.
No novel reasoning, loop escape or truncated-response repair is added.

Native max-tokens at the matched4096 limit is a measured task failure. It does
not cause automatic cap increases, result replacement or paid retries. Shared
transport/auth/environment failures pause new admissions, preserving evidence.

Grading uses the pinned official tests/images/parser on the academy server after
freezing each source artifact. The model-free local relay must stay online for
timely transfer; solving on Cube does not depend on the local relay being online.
The user enters a fresh key locally. It is sent only via encrypted SSH stdin,
consumed from 0600 tmpfs and unlinked. Task processes only see per-job proxy tokens.
