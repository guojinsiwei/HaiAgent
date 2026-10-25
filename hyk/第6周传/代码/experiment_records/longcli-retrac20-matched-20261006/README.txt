Re-TRAC matched-resource LongCLI20 experiment, 2026-10-06

Source: C:/Users/54177/Desktop/retrac-handoff.zip
SHA256: abce18298d86989975885209621b767da29b416c866e7b3233d687475f31a50e
The 24 handed-off source/contract files are unchanged and manifest-verified.
This is the user's independent paper-grounded implementation, NOT an official
author release or the trained RE-TRAC model. Only deployment adapters are added.

Same fixed20 tasks/official commit, deepseek-flash, thinking disabled, temp0.
800 logical model requests including compression and format repair; two HTTP
attempts per request,1600 hard wire ceiling;600 terminal calls,4096 output tokens.
Final input JSON messages <=48000 UTF-8 bytes; observations <=24000 bytes,
with JSON escaping charged. No hidden removal of earlier messages in transport.
AP26/AP35 wall10800 seconds, others7200; wait/command bound300 seconds.
Two CPU cores and3GiB address space per process, same frozen rootfs/toolchains.
Each task has a separate fresh rootfs/home/shell and independent recursive state.

Preserve original defaults:8 rounds, full8-facet memory,50 action responses per
round,2 format attempts. Those are algorithm-specific settings, not DH/DSH knobs.
Byte-budget subclass overrides only size accounting and bounded observations.
No solver/compression/continuation prompt modifications and no DSH memory gate.
Context reserve12000 bytes, maximum state8000 characters (within output allowance).
No use of hidden tests/grades to select a rollout or trigger another attempt.

Cube cannot Docker; a persistent PTY in a private user/PID/network namespace
substitutes for tmux. Newlines, cwd, exports, control keys and process persistence
are retained within a task; external networking and host/hidden-test access denied.
The handed-off native LongCLI adapter itself is unchanged; its engine is invoked
by this deployment adapter, not claimed to be a Docker/tmux run on Cube.
Official grading remains unchanged on the academy server, sequential8CPU/8GiB.
Historical DH counts characters, DSH pays native tool-schema input bytes; these
are not identical token budgets or tool interfaces. Report these differences.

The queued workers wait for BOTH current DSH workers to release their task slots
before making model calls. Keys come from fresh local hidden input and live in
controller RAM only; temporary0600 tmpfs launch handoff is immediately unlinked.
No reused credentials, no key in task environment/arguments/logs, no auto retries.
Result relay is ordinary Python, has no model API access and uses no GPT task.
Keep this computer online for timely artifact return/official grading.

Keyless acceptance must verify eight actual rollouts,seven recursive compressions,
early-evidence use, persistent shell state, Ctrl-C, resource caps,/dev/null,
external network/hidden-test isolation,UTF-8 budget and unchanged source manifest.
It does not prove real-model task success or exact reproduction of paper results.
