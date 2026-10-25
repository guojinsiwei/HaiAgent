Official DeepSeek Harness LongCLIBench 20-task repair rerun

Original campaign retained: longcli-dsh20-20261005. Never overwrite its jobs or scores.
New campaign: longcli-dsh20-repair1-20261005.

Failure evidence: output allowances collapsed to 739 or 1 token; provider finish_reason=length;
native turn_end=max-tokens, but old scheduler ignored native_error and admitted further jobs.
Repair: actual DeepSeek Flash adapter context capacity 1,000,000 tokens, native compaction
headroom 65,536 tokens, summary output cap 2,048. Capture exact native and provider finish reasons.
Pause new admissions on any non-budget native failure or provider transport failure, even
if earlier tools executed. No automatic retry of a failed task.

Unchanged: official npm DSH 0.2.0-rc.2, DeepSeek Flash, thinking disabled, temperature 0,
4096 output tokens per model call, 800 total API attempts / 600 root tools / 7200 seconds per task.
First real task must exit normally before permitting four parallel solvers.
Every task gets a NEW container, workspace, DSH home and private network. Grading is separate.

Verification: budget tests, controller stop tests, all20 task environment checks, two native
fresh-container tool loops, a 32-step native context-pressure test and official grading roundtrip.
Mock tests validate wiring and budgets, not real model quality. The first paid task is the live pilot.

Context is NOT matched to historical DH's 48000 characters; platform and retry differences also
remain. This is a practical comparison, not a strict single-factor ablation. Report these differences.

Launch: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "Start-DSH20.ps1"
Fresh API key is entered via hidden local input and encrypted SSH stdin; no key in task containers.
Launch script never reuses previous experiment credentials. No GPT-based recurring monitoring.
