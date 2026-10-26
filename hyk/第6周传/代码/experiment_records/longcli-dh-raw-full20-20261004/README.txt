DH versus RAW — full fixed LongCLI-Bench comparison, 2026-10-04

20 official tasks per arm, 40 fresh trials. Commit:
2015f37b5c458f2562354de6b415e9182c91af64.
The terminal-bench_task scaffold is excluded.

DH = repaired v9 + recovery scheduling counter fix + existing prediction
extension switch set to false. Orthogonal exploration, conditional memory,
monitor and advisor are enabled. No graph search. Frozen sources live in
sources/bestfgs-project/src/bestfgs; their provenance/hashes are recorded in
dh-source-manifest.json. Previous releases and recorded results remain intact.

RAW uses the frozen linear raw runtime, without memory/monitor/advisor/search.
Both arms share the strict JSON wire, repaired devices, toolchain images,
isolated executor, public task inputs and final official grader.

deepseek-flash, thinking disabled, temperature 0. Per task: 800 total logical
decision requests, 600 actual tool calls, 48000-character context limit,
4096 actor output tokens. Wire retries are separately counted/audited, as in
the previous comparison. Official task wall/test timeouts are preserved.
Two containers, two slots each, four concurrent trials total. The first four
trials are paired scheme/ants checks and belong to the full result set.

All 20 unchanged starter artifacts are graded before paid generation. Baseline
P2P failures are recorded in grading-acceptance.json and do not automatically
mean a solver introduced a regression. Raw official grades remain unchanged.
Interpret F2P, P2P and combined success separately. Grader failures/missing
reports are infrastructure outcomes, not silently converted to zero scores.

Offline preparation may reuse each toolchain while replacing the entire public
/app for every fixture. Paid trials always receive fresh independent rootfs
copies. No official tests or controller credentials are in solver workspaces.

Start-DH-RAW-Full20.ps1 opens hidden local credential input after all seals
validate. The key goes through SSH stdin to private tmpfs, never chat, arguments
or logs. Workers run independently on the cloud after launch. The local Python
relay requires this computer to remain online for automatic grading triggers
and result downloads. It makes no model/GPT requests.

Progress: paired-status.json (local), health-0.json/health-1.json (cloud).
Evidence and returned results: received/<arm>--<task>/.
No automatic task replay or algorithm changes. Shared terminal wire/provider
faults stop new admissions and preserve all already admitted work/results.
