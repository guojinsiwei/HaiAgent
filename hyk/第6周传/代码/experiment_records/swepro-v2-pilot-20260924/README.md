# SWE-bench Pro V2 HARD-50 paired experiment

Purpose: compare BestFGS v13 with a raw sequential baseline on the same 50
difficult SWE-bench Pro V2 tasks. Each method receives every task, for 100
method runs in total.

## Frozen protocol

- Task IDs: `hard50_ids.txt` (50 unique members of official HARD-51).
- Selection rule: deterministic SHA-256 ordering with seed `20260924`; no
  outcome-based selection or runtime replacement.
- Selection SHA-256:
  `381f9e131112c2779c61ad24afc678755b3c0147ef050ca4c328d301defeb7fd`.
- Model: DeepSeek `deepseek-flash`, direct API, temperature 0.2.
- Equal per-method limits: 33 decisions, 108 CLI calls, four commands per
  action, 3000 seconds; adaptive budget disabled.
- BestFGS: graph engine plus conditioned experience; blocking memory off.
- Raw: sequential evidence engine, experience off, branching off, blocking
  memory off.
- Method order alternates by task hash. The Git workspace is reset and cleaned
  to the same recorded base commit before every arm.
- Two CubeStudio workers receive 25 fixed tasks each.

## Frozen code

- Release: `releases/branching-memory-v13`.
- Archive SHA-256:
  `008fcdf83dd2c248d1f78d1cc907d24d80ffd5a2ace20a987c141d17e6d04391`.
- Regression gate: 636 tests pass locally and on cloud Linux. The revision
  includes one Linux compatibility correction allowing verified Python
  executables up to 128 MiB to be hashed for evidence-cache identity; task-file
  reads retain the 16 MiB limit.

## Execution and evaluation boundary

- Agent-visible metadata contains only the instruction and public task
  configuration; gold patches and verifier files are excluded.
- Official images are cached with `skopeo`, unpacked with `umoci`, and entered
  through `proot` using a fixed Agent Python runtime.
- Only patches, trajectories and metrics are exported from CubeStudio.
- Authoritative scoring must replay patches in fresh official images with the
  unchanged V2 verifier on a Docker/Harbor-capable machine.
- CubeStudio cannot enforce official agent-phase network isolation. These are
  paired development results, not an official locked-protocol leaderboard run.

Image preparation does not call the model or consume API credit.
