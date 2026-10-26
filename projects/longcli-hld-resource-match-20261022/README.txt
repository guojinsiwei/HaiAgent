LongCLI HLD v8 resource-limit rerun
=================================
Started: 2026-10-22 23:50:44 Asia/Shanghai
Remote: /mnt/sdb/home/lizh639/longcli-hld-resource-match-20261022
Supervisor PID: 3319094

Selection: first-pass HLD functional score lower than historical Recuris,
AND first-pass HLD limited to 400 requests / 16,384 output tokens.

Matched tasks:
cs61_fa24_scheme: HLD 92.8571%, Recuris 100%; fresh attempt started.
61810_cow: HLD 55.4545%, Recuris 73.6364%; fresh attempt started.
ap1400_2_hw26: HLD 37.5%, Recuris 100%; reuse completed raised-limit
attempt in ../longcli-hld-hw26-matched-20261022, also 37.5%.

61810_fs and 61810_mmap are excluded: already used 800 / 32,768 caps.

Configuration: frozen HLD v8, deepseek-flash via saved TaoToken route,
800 total model requests, 32,768 maximum output, 128,000 context,
32,768 compaction headroom, 600 tools, 7,200 solver seconds,
2 CPU / 8 GiB per container. Two concurrent tasks, no automatic paid retry.
Each fresh attempt <=24 CNY, all roles included; maximum new spend 48 CNY.
Charges remain in the original 480 CNY campaign ledger; no reset/repricing.
The original 20-task scores are retained and never overwritten by these reruns.

This repeats the raised-limit HW26 configuration. Historical Recuris used
1,000,000 context and 65,536 headroom; these are NOT fully identical resource
configurations. HLD monetary caps had already been 24 CNY; the smaller limits
here refer to requests/output, not a smaller monetary cap.

Preflight: original starter/image/instruction and official grader AST/hashes
verified, HLD source sealed, budget guards tested offline. Actual container
entry refused the isolated 1-microCNY test ledger before any provider response;
paid model calls in entry probe: zero.

Launch verification at ~23:51:15: both tasks solving, Scheme 6 and COW 7 HTTP
200 responses; no HTTP errors/provider stops/budget stops. Effective limits
recorded in each job logs/live/effective-limits.json.
Other active LHTB and v9 tasks were not modified or restarted.
