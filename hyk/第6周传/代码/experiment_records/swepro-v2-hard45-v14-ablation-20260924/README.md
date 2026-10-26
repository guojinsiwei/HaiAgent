# SWE-bench Pro V2 HARD-45 v14 four-arm ablation

This is a preregistered paired development experiment. It does not claim an
official locked-network SWE-bench Pro score.

## Frozen design

- Population: 45 tasks selected before outcomes from the previously frozen
  HARD-50 by ascending `SHA256("v14-hard45\\0" + instance_id)`.
- Selection SHA-256: `e4f9cc31442d418cc0d4cdacb830603b053497c5b1a49c97f167a8f369bcccdb`.
- Every task runs all four arms: `raw`, `memory_only`, `search_only`, `bestfgs`.
- Factorial meaning: sequential/graph search × off/conditioned task-local memory.
- The same task, model, temperature, decision/tool budget, prepared image,
  submission gate and later official evaluator are used in every arm.
- Two CubeStudio containers retain the existing immutable image-cache
  assignment: worker 0 has 23 tasks and worker 1 has 22 tasks.
- Within each task, arm order cycles deterministically through all 24
  permutations. No order depends on an outcome.
- Model: DeepSeek `deepseek-flash`, temperature 0.2.
- Per arm: 33 decisions, 108 actual CLI calls, at most four commands per action,
  3000 seconds, adaptive budget disabled.
- A normal terminal run, including model-output-format failure, is never rerun.
  Only infrastructure failures may resume, at most three attempts per task-arm.
  The cloud guard has at most 20 process-level recoveries and never bypasses the
  per-arm cap.

## Frozen artifacts

- v14 archive SHA-256:
  `035397290233db3b48d14983135275b0a1fb34a65c7f45f9dab8788f3a87f6ad`
- Reused frozen cache-controller SHA-256:
  `158a2059e713b6df46fc657527edb5fb5c10750e95e585c6de17af4d73e47bb6`
- Four-arm scheduler SHA-256:
  `c9843f39c8ff4270b8bc5e17c7260a4f9c4f95888a6fbb6c6fcf366ba4d8461a`
- Runtime/report versions are recorded in `branching-memory-v14/VALIDATION_V14.json`.
- Local full regression: 637 tests, 0 failures/errors, 26 environment skips.
- Both cloud containers must independently pass the same Linux regression before
  the start script accepts a key.

## Start and status

Run `Start-SWEProHard45-V14.ps1` locally. It validates both workers first, then
prompts for the DeepSeek key without echoing or writing it to disk. Run
`Check-SWEProHard45-V14.ps1` for progress. Image preparation consumes no model
credit and continues in the existing cloud cache workers.

Official scoring is a separate later replay of the exported patches in fresh
official images. The cloud run must not label internal submission as official
success.
