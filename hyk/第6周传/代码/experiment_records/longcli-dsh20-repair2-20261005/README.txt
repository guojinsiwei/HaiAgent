Official DeepSeek Harness LongCLIBench repair2: uniform20 fresh rerun

Root cause: CMU P0/P1 emitted write tool arguments exceeding the artificial4096-token
single-call limit. Both API responses stopped with finish_reason=length at exactly4096.
Fix: native pi-ai default32768 at all three layers: model configuration, instrumentation,
and host relay. Native title/summary lower caps are preserved (64/2048 etc.).

Model unchanged: DeepSeek Flash, thinking disabled, temperature0, official DSH0.2.0-rc.2.
No repetition feedback, no DH memory/orthogonality, no new decision logic. DSH's own
repetition is an experimental outcome, not silently repaired or excluded from averages.
Context1M, headroom65536, summary2048. Per task800 total API attempts /600 root tools /7200s.
First real task is previously truncated CMU P1. Native abnormal termination pauses admissions.
After a normal pilot, four solvers and one official grader. Every task uses a new container,
home, workspace and isolated network. Never reuse previous task sessions or credentials.

All20 tasks rerun with uniform configuration; previous passes and failures retained, not
selectively combined with new outputs. Old DH20 remains the historical comparator.
NOT an equal-budget/context single-factor ablation: historical DH had output4096, context48000
characters and a different execution/retry setup. A higher response allowance may consume more
tokens; report all usage. No unbounded response cap or automatic failed-task replay.

Keyless verification: 20 environments, budget tests, native isolation loops,32-step context
pressure test, large native write fixture and failing4096 control, official grader roundtrip.
Mock token pressure is a deterministic simulation, not actual tokenizer or model testing.
The paid CMU P1 pilot is the first real validation after hidden local API-key input.

Launch: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "Start-DSH20.ps1"
Server: /var/tmp/lizh639-longcli-dsh20-repair2-20261005
No GPT-funded recurring monitoring tasks. The model-free local relay only returns status/results.
