KZ2.0 cow-timeout-retry1
Base: KZ2.0 memory-prose-soft-retry1. Cow only, fresh container and memory.
The actor's timeout_seconds=60 was used directly; a Docker layer also capped
all commands at 300, making 'sleep 400; read log' impossible.
Repair: the harness owns the actor command window, configured to 600 seconds.
Model timeout values are audited but cannot shorten/extend that window.
Docker dispatch caps by the configured window and the remaining task deadline.
The model receives the real execution window and timeout-specific feedback.
argv/stdin and stdout/stderr are not rewritten or fabricated. Timed-out commands
remain failed/incomplete observations, never completed test verdicts.
Internal preflight and state probes keep their independent short timeouts.
Only command_seconds changes (300 -> 600). Each task still has 7200 seconds,
800 API requests across roles, 600 tools, 1M context, 32768 output, and CNY50.
deepseek-flash, thinking disabled, temperature=0; no new exploration mechanism.
Keep old cow artifacts, lock's score, and running mmap/cmu_p2 attempts intact.
