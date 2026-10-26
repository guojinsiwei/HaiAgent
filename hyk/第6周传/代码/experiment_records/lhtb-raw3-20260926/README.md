# LHTB Raw 3: loop diagnostic, not official evaluation

Deployment: college `lizh639@172.16.108.236`, directory
`/mnt/sdb/home/lizh639/lhtb-raw3-20260926`. Local computer only uploads/launches/retrieves.
Do not restart the older HAI terminal6 pilots with this launcher.

Official source: https://github.com/zli12321/LHTB at
`d78f5eb52ad754c5ee9154741af73130a85a65b8`.

Three public CPU tasks selected before model results:

1. `langchain-version-migration`: offline legacy API migration.
2. `nbody-accel-iterative`: iterative numerical optimization and correctness.
3. `duckdb-optimizer-closure`: repository-level optimizer work and benchmarks.

Run serially, one fresh container per task. Respect original 2–4 CPU/4–8 GiB
task limits; no GPU. Host-wide resources are shared, not our allocation.
Image downloads use official manifest digests via the previously used transport
mirror. Stop if disk reserve is low. Do not delete others' images/containers.

Raw is the existing HAIAgent 0.4.0 runtime with `method=raw`, which bypasses its
memory/context/repetition intervention. Existing plain conversation history and
48,000-byte prompt truncation remain. This is a scaffolded Raw baseline, not a
claim about the model independent of its interface/context budget.

Model `deepseek-flash`, official DeepSeek endpoint, thinking disabled,
temperature 0, tool-call protocol; 3 tasks x 1 attempt, concurrency 1.
Per task: 90 min, 320 strategy responses, 300 tool calls, command limit 900 sec,
4096 output tokens per response, 16,000 bytes tool output. No task auto-retry.
Transport retries at most 2 per request. No added anti-loop guidance/intervention.

This intentionally differs from official LHTB: stock Harbor single-shot run,
explicit autonomous-submit override, no continue-until-timeout after verifier
rejection. Some tasks' official limits are longer. Verifier disabled: successful
submission **is not official success**, all success rates remain null. Public
bench/check commands remain available. Therefore no leaderboard comparisons.

Preparation runs under tmux without any model calls; ready.json is written only
after all three scripted command→feedback→submit fixtures succeed. Launch asks
for the key hidden in local PowerShell; key travels through SSH stdin and is
consumed/unlinked from a mode-0600 /dev/shm file. No key is written into source or
logs. Launch checks model availability without generation. Existing health/trials
prevent duplicate launches. tmux survives local shutdown, not server shutdown.

`observe.py` only reads traces. It flags 5 identical consecutive action/results,
or period-2/3/4 cycles repeated 3 times. These are candidate windows, NOT the
tool-redundancy metric and NOT automatically proof of a dead loop. Review state,
polling intent, new evidence, repeated hypotheses and strategy changes manually.
Also inspect semantic repetition with differing command text (detector misses it).
Infrastructure/network/timeout failures are not model loops. Preserve prompt
omission counts to distinguish context-induced repetition.

No change to running research code, no automatic official grading, no recurring
GPT monitoring. This 3-task convenience sample only assesses feasibility; a
negative result cannot prove LHTB lacks loops and a positive result cannot prove
our memory method works.
