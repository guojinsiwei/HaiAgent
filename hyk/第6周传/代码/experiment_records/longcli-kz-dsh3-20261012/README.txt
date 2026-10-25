LongCLIBench 3-task KZ migration regression — 2026-10-12
======================================================
New arm: current official DSH 0.2.0-rc.2 + KZ plugin 0.2.4, no source algorithm changes.
Only three new paid tasks authorized. Do NOT run native DSH, old KZ, or TerminalBench.
Tasks: cs61_fa24_hog, cs61_fa24_cats, ap1400_2_hw35.

Historical KZ scores: all 1.0. Official success flags are true / false / true,
respectively: a score of 1.0 is not automatically official success (P2P matters).
Historical requests/tools: hog 36/22; cats 19/14; ap35 27/23.
Source: ../longcli-dh-1342-complete20-20261009/KZ-results20.json.
Frozen benchmark commit 2015f37b5c458f2562354de6b415e9182c91af64;
same task instructions, starter archives, task-image hashes, official grading code.

Budget: 800 requests shared by solver/monitor/advisor/critic/compaction;
600 total tools INCLUDING KZ metadata; 7200 seconds; model deepseek-flash;
context 1000000, solver/roles output 32768, temperature 0, thinking disabled.
Native compaction output explicitly 32768, headroom default 65536;
compaction temperature is native omitted, not falsely reported as zero.
Native DSH bash foreground/background mechanics retained (not the old stateless shell).
2 CPU/8 GiB/256 PIDs per solve. First hog pilot, then cats/ap35 max 2 concurrent.

Not a controlled scientific ablation: TaoToken route/model revision may differ;
DSH execution and compression differ; rollback remains frozen as requested;
historical shell counts are not equivalent to new metadata+native tool counts.
This is intentionally a regression of previously strong tasks, not a random sample.

Current KZ limitations from the TB4 trace are NOT silently patched in this run:
memory-path validation and evidence visibility rules remain; native todo does not
automatically become KZ subgoals. This run checks actual behavior with adequate budget.
Audit admitted memories / retrieval / action binding, subgoals, Monitor/Advisor,
Critic receipts, actual test calls, refusals, compression and all-role API costs.
Passing a task does not prove every module worked; absence of a needed trigger is
not automatically a module failure.

Cost guard: 50 CNY per task using historical 2/8 CNY per million upper estimates.
This is NOT a TaoToken TokenPlan invoice, quota meter, or reliable cash deduction.
Request and tool caps are independent enforced bounds. No automatic paid retries.

All task containers, workspaces, homes, networks and memory are freshly isolated.
Real key travels via SSH stdin then Docker stdin, never arguments, files or logs.
Only API HTTPS CONNECT allowed by campaign proxy; official tests are withheld.
Official grader uses a separate fresh container and immutable final source archive.
On pilot engineering failure, preserve results and stop admitting remaining tasks.
Normal low score does not stop the remaining tasks. No GPT automation or mail.

Remote: /var/tmp/lizh639-longcli-kz-dsh3-20261012
Start: powershell.exe -NoProfile -ExecutionPolicy Bypass -File Start-LongCLI3.ps1
Read-only status: status.py; public result cache: latest-status.json.
Offline acceptance: ready.json (172 tests, 3 image checks, native compaction,
official starter grading), zero provider calls. Real performance is not yet known.
