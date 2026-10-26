# LongCLI Raw 3: single-final-grading diagnostic

Purpose: determine whether a standard sequential CLI agent exhibits repeated
no-progress tool use. No memory, graph search, anti-loop interventions, or online
hidden-verifier feedback. A negative finding (no loops) is a valid result.

## Frozen plan

- CubeStudio worker 0, directory `/mnt/lizh639/longcli-raw3-20260927`.
- Pinned LongCLI commit `2015f37b5c458f2562354de6b415e9182c91af64`.
- Tasks: cs61_fa24_scheme, cs61_fa24_ants, cs61_fa24_cats. This is a Python/Scheme
  subset chosen for common runtime availability, not model outcomes; not the whole benchmark.
- Frozen HAI runtime snapshot with `method=raw`; memory component is disabled.
- DeepSeek official endpoint, deepseek-flash, thinking disabled, temperature 0,
  maximum output 4096 tokens. `/models` authorization check refuses model substitution.
- 7200 seconds / 800 action turns / 600 tools per task, whichever comes first;
  commands capped at 300 seconds; transport at most 2 attempts per request.
- Sequential, three runs only. Model submission ends a run. No automatic rerun
  of poor results or restart of interrupted tasks. API errors stop remaining tasks.
- Prompt cap 48000 UTF-8 bytes, bounded tool output 16000 bytes. Full actual request
  messages and model response objects are audited; tool output includes hashes,
  head/tail and explicit truncation flags. These are finite-context Raw results.

## Acceptance evidence and isolation

`acceptance.json`: official tests distinguish a correct public Frame implementation
(partial F2P 1/28) from an incorrect one (0), and reject protected-file tampering.
This is a positive subsystem fixture, not a full-task oracle. Starter-source transfer
and scoring equivalence were separately checked for Scheme and C++.

`isolation-result.json`: capability removal, no_new_privs, no host/shared/SSH/secret
access, network isolation, no re-chroot, protected workspace root, writable task data.
Bubblewrap mount operations are unavailable on CubeStudio. Instead, commands run
as host UID 65534 in new user/PID/network namespaces, then chroot into a private
official-image export and drop all capabilities. No host proc, Docker socket, hidden
tests or credentials are inside. System files stay owned by host root; only task
data/temp are owned by the sandbox identity. Each command's namespace is ephemeral;
background services and network access are deliberately unsupported in this subset.
CPU affinity is 2 CPUs; address space is 3 GiB per process, file size 256 MiB,
and process/FD limits apply. These are not a separate Docker cgroup memory quota;
the existing CubeStudio total cgroup is the outer resource limit.

## Start and inspect

Run `Start-LongCLIRaw3.ps1` locally; enter key privately. It authenticates without
inference and detaches a locked tmux worker. Do not send credentials in chat.
No paid run has started merely because `ready.json` exists.

Inspect cloud `health.json`, `summary.json`, `runs/<task>/events.jsonl` and
`artifacts/<task>.tar.gz`. Finished artifacts are hashed; symlinks, special files,
oversize exports fail closed rather than following paths on the host.

Final grading is separate, in fresh pinned Docker environments with untouched
official tests. Never use LongCliParser's placeholder PASSED flag as task success.
Report F2P, P2P and full success only with nonempty test coverage. Model submission
and exit zero do not establish success. Do not import controller logs into /app.

## Loop analysis (offline only)

Report exact repeated actions/results and periods of unchanged source state as
candidate no-progress episodes, with timestamps and model-visible evidence.
Inspect candidates semantically: polling, necessary revalidation and changed state
are not automatically redundant. Keep failed actions that lead to useful strategy
changes distinct from unproductive loops. Report task-level examples, total calls,
turns, tokens and wall time; do not rename mechanical repetition as semantic redundancy.

Status is recorded in cloud health files; this document is not a live monitor.
