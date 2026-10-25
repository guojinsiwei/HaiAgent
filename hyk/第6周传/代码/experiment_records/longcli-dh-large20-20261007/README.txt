DH historical-best + DSH-large resource envelope, LongCLIBench full20

Historical DH source: longcli-dh-raw-full20-20261004, recovery-counter-fix-v9.
Historical matched DSH: longcli-dsh20-repair2-20261005, ACTUAL runtime settings.
Native DH memory, monitor, advisor, orthogonal gate, no graph search, no predictions.

Matched: deepseek-flash; thinking disabled; temperature 0; 1,000,000-token context
allowance with 65,536-token headroom; 32,768 output tokens on every DH role;
800 actual provider attempts across all roles and retries; 600 model-requested tools;
7,200 seconds per task (including ap26/ap35); 300-second tool timeout;
2 CPU, 8GiB, 256 PIDs per fresh solver container; pilot then concurrency 4;
same20 immutable public starters/images/official grader, 8CPU/8GiB serial grading.

Not an identical harness: native DH JSON wire, stateless shell, memory and context
excerpt logic are intentionally retained. DSH native tool/session/compaction/title
algorithms are NOT imported. DSH has a heuristic token meter, NOT an exact tokenizer;
the same UTF-16-length/4 + structural-overhead estimator is used for DH history.
DH command result projection (24,000 bytes), monitor window and memory reserve
remain native algorithm settings. Network disabled for tools; host calls provider.
DH bounded nonstreaming wire (90-second request/180-second logical retry allowance)
is retained, versus DSH streaming transport. No claim of bit-identical interfaces.
Only native code change: argv/stdin character allowance 24,000 -> 524,288.
Budget adapter changes full-history capacity and strict response capacity, not strategy.
OS per-argument limits remain; large content can use stdin, not arbitrary-size argv.

Storage incident: /var/tmp returned actual ENOSPC during deployment. This new run's
workspace, logs, homes and /tmp bind mounts are on /mnt/sdb/home/lizh639 instead.
Docker daemon location is unchanged. A zero-API official grading roundtrip is
required before key input. Other experiments and existing data are untouched.

No paid run until acceptance.json and grading-acceptance.json both pass, source
hashes verify, and the user enters a NEW key in Start-DH-Large20.ps1.
Key only in RAM through SSH stdin/fork, never in arguments/files/environment/logs.
One included pilot, then four concurrent tasks. Engineering errors stop admissions
and active paid children. No automatic retries, no GPT scheduled monitoring.
Official scoring continues server-side. Run status.py for compact public status.
